import "server-only";
import { query, queryOne } from "@/lib/db";
import { decryptPassword } from "@/lib/agent-crypto";

const LATEST_AGENT_VERSION = "2.2.1";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const token = url.searchParams.get("token");
  const version = url.searchParams.get("version") ?? null;
  if (!token) return new Response("Unauthorized", { status: 401 });

  const agent = await queryOne<{
    id: number; customer_id: number; subnets: string | null;
    wmi_user: string | null; wmi_pass: string | null; snmp_communities: string | null;
    ad_sync_enabled: boolean; ad_sync_default_group_id: number | null;
  }>(
    "SELECT id, customer_id, subnets, wmi_user, wmi_pass, snmp_communities, ad_sync_enabled, ad_sync_default_group_id FROM network_agents WHERE token=$1",
    [token]
  );
  if (!agent) return new Response("Unauthorized", { status: 401 });

  await query(
    "UPDATE network_agents SET last_seen=now(), agent_version=$1 WHERE id=$2",
    [version, agent.id]
  );

  // 15 dakikadan uzun süre running'da kalan komutları error'a al
  await query(
    `UPDATE agent_commands SET status='error'
     WHERE agent_id=$1 AND status='running'
       AND created_at < now() - INTERVAL '15 minutes'`,
    [agent.id]
  );

  // 2 saatten eski pending komutları temizle (test artıkları, çökmeden kalan stale komutlar)
  await query(
    `UPDATE agent_commands SET status='error', result='stale-cleanup'
     WHERE agent_id=$1 AND status='pending'
       AND created_at < now() - INTERVAL '2 hours'`,
    [agent.id]
  );

  const commands = await query<{ id: number; command: string; params: Record<string, unknown> }>(
    `SELECT id, command, COALESCE(params, '{}') as params
     FROM agent_commands
     WHERE agent_id=$1 AND status='pending'
     ORDER BY created_at ASC LIMIT 10`,
    [agent.id]
  );

  if (commands.length > 0) {
    await query(
      `UPDATE agent_commands SET status='running' WHERE id = ANY($1::int[])`,
      [commands.map(c => c.id)]
    );
  }

  const subnets = agent.subnets
    ? agent.subnets.split(",").map(s => s.trim()).filter(Boolean)
    : [];

  const snmpCommunities = agent.snmp_communities
    ? agent.snmp_communities.split(",").map(s => s.trim()).filter(Boolean)
    : ["public"];

  // AD / LDAP config
  const adCfg = await queryOne<{
    enabled: boolean;
    dc_host: string | null; domain_name: string | null; base_dn: string | null;
    bind_username: string | null; bind_password_enc: string | null;
    sync_interval_hours: number;
  }>(
    "SELECT enabled, dc_host, domain_name, base_dn, bind_username, bind_password_enc, sync_interval_hours FROM customer_ad_config WHERE customer_id=$1",
    [agent.customer_id]
  );

  let adConfig = null;
  if (adCfg?.enabled && adCfg.dc_host) {
    let bind_password = "";
    try {
      bind_password = adCfg.bind_password_enc ? decryptPassword(adCfg.bind_password_enc) : "";
    } catch { /* silently skip decrypt errors */ }
    adConfig = {
      enabled: true,
      dc_host: adCfg.dc_host,
      domain_name: adCfg.domain_name ?? "",
      base_dn: adCfg.base_dn ?? "",
      bind_username: adCfg.bind_username ?? "",
      bind_password,
      sync_interval_hours: adCfg.sync_interval_hours ?? 6,
    };
  }

  console.log(`[agent/poll] agent=${agent.id} customer=${agent.customer_id} cmds=${commands.length} ad=${!!adConfig}`);
  return Response.json({
    commands,
    subnets,
    latest_version: LATEST_AGENT_VERSION,
    wmi_user: agent.wmi_user ?? "",
    wmi_pass: agent.wmi_pass ?? "",
    snmp_communities: snmpCommunities,
    ad_config: adConfig,
  });
}
