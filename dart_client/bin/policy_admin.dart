// Policy Admin — pure Dart, runs as the Policy Admin atSign (@route_policy_admin / @kilo)
// and exposes the access policy as a small web page. Toggling a publisher pushes the new
// grant set to the policy engine (@route_policy / @juliet), which persists + republishes it.
//
// Segregation of duties: the admin (@kilo) governs access from a different identity than the
// policy engine (@juliet) and the planner (@alpha).
//
// Run (keys in $HOME/.atsign/keys):
//   dart run bin/policy_admin.dart --atsign @kilo --root-domain vip.ve.atsign.zone
// then open http://127.0.0.1:8090
import 'dart:convert';
import 'dart:io';

import 'package:at_client/at_client.dart';
import 'package:at_cli_commons/at_cli_commons.dart';

const int kPort = 8090;
const String kNamespace = 'smartroute';

late AtClient atClient;
late String me;            // @kilo
late String engineAtSign;  // @juliet (policy engine)
final Map<String, String> roleToAtSign = {}; // role -> atSign (publishers only)
final Set<String> granted = {};               // authorized atSigns, as held by the ENGINE
bool synced = false;                          // has the engine told us its rule set yet?

// Which config column to use: 'ee' (local test env, default) or 'vanity' (production).
// Matches the Python services' ATSIGN_PROFILE env var.
final String profile = Platform.environment['ATSIGN_PROFILE'] ?? 'ee';

/// Locate config/ee_atsigns.json whether run via `dart run` or as a compiled binary.
/// Order: ATSIGN_CONFIG env, cwd, then locations relative to script/executable.
File _findConfig() {
  final scriptDir = File.fromUri(Platform.script).parent.path;
  final exeDir = File(Platform.resolvedExecutable).parent.path;
  final candidates = <String>[
    Platform.environment['ATSIGN_CONFIG'] ?? '',
    'config/ee_atsigns.json',
    '$scriptDir/../../config/ee_atsigns.json',
    '$scriptDir/config/ee_atsigns.json',
    '$exeDir/config/ee_atsigns.json',
    '$exeDir/../config/ee_atsigns.json',
  ];
  for (final p in candidates) {
    if (p.isNotEmpty && File(p).existsSync()) return File(p);
  }
  throw StateError('Could not find config/ee_atsigns.json. Set ATSIGN_CONFIG or run '
      'from the repo root. Tried:\n  ${candidates.where((c) => c.isNotEmpty).join("\n  ")}');
}

Future<void> _loadRoles() async {
  final cfg = jsonDecode(await _findConfig().readAsString()) as Map<String, dynamic>;
  final roles = cfg['roles'] as Map<String, dynamic>;
  engineAtSign = (roles['policy'] as Map)[profile] as String;
  for (final entry in roles.entries) {
    final role = entry.key;
    if (role.startsWith('intxn_') || role.endsWith('_feed')) {
      roleToAtSign[role] = (entry.value as Map)[profile] as String;
    }
  }
}

/// Track the engine's rule set. The engine owns it and mirrors every change (and a
/// heartbeat) here, so the page shows what is actually enforced. The admin deliberately
/// does not seed or push a set at startup: doing so would overwrite the operator's
/// revocations every time this process restarted.
void _watchEngine() {
  atClient.notificationService
      .subscribe(regex: kNamespace, shouldDecrypt: true)
      .listen((notification) {
    // The sender check is what matters: only the engine may state the rule set.
    if (notification.from != engineAtSign ||
        !notification.key.contains('policy')) {
      return;
    }
    try {
      final data = jsonDecode(notification.value!) as Map<String, dynamic>;
      final engineGrants =
          (data['grants'] as List).map((g) => g as String).toSet();
      final changed = !synced ||
          engineGrants.length != granted.length ||
          !engineGrants.containsAll(granted);
      granted
        ..clear()
        ..addAll(engineGrants);
      synced = true;
      if (changed) {
        stdout.writeln('[policy-admin] engine rule set is now '
            '${granted.length} publisher(s): ${granted.toList()..sort()}');
      }
    } catch (e) {
      stdout.writeln('[policy-admin] unreadable policy from $engineAtSign: $e');
    }
  }, onError: (e) => stdout.writeln('[policy-admin] subscription error: $e'));
}

Future<void> _pushGrants() async {
  final key = AtKey()
    ..key = 'admin'
    ..namespace = kNamespace
    ..sharedBy = me
    ..sharedWith = engineAtSign
    ..metadata = (Metadata()..ttl = 86400000);
  final value = jsonEncode({
    'grants': granted.toList(),
    'version': DateTime.now().millisecondsSinceEpoch,  // engine ignores stale/replayed versions
  });
  final res = await atClient.notificationService
      .notify(NotificationParams.forUpdate(key, value: value));
  stdout.writeln('[policy-admin] pushed ${granted.length} grants to $engineAtSign '
      '(${res.notificationStatusEnum})');
}

String _html() {
  final roleList = roleToAtSign.keys.toList()..sort();
  final rows = roleList.map((role) {
    final at = roleToAtSign[role]!;
    final on = granted.contains(at);
    return '<tr><td>$role</td><td class="at">$at</td>'
        '<td><label class="sw"><input type="checkbox" data-role="$role" '
        '${on ? 'checked' : ''} onchange="toggle(\'$role\', this)">'
        '<span></span></label></td></tr>';
  }).join();
  final rolesJson = jsonEncode(roleToAtSign);
  return '''<!doctype html><html><head><meta charset="utf-8">
<title>Route Policy Admin</title><style>
 body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#101828;color:#eef;margin:0;padding:32px}
 h1{margin:0 0 4px} .sub{color:#9fe7e7;margin-bottom:24px}
 table{border-collapse:collapse;width:100%;max-width:720px;background:#16203a;border-radius:12px;overflow:hidden}
 td,th{padding:12px 16px;text-align:left;border-bottom:1px solid #24304f}
 .at{color:#9fb;font-family:monospace} th{background:#0e8c8c}
 .sw input{transform:scale(1.5)} #status{margin-top:18px;color:#13b513;font-weight:600}
 .who{color:#b8c0cc;font-size:13px;margin-top:24px}
</style></head><body>
 <h1>Route Policy Admin</h1>
 <div class="sub">Signed in as <b>$me</b> · changes pushed to engine <b>$engineAtSign</b> · default-deny</div>
 <table><tr><th>Role</th><th>atSign</th><th>Authorized</th></tr>$rows</table>
 <div id="status">Waiting for the engine's current rule set…</div>
 <div class="who">Toggle a publisher to grant/revoke. The planner enforces this within seconds;
   revoked publishers are dropped (default-deny). The switches show what the engine holds,
   refreshed every few seconds, so a change made elsewhere appears here too.</div>
<script>
 const roles = $rolesJson;
 async function toggle(role, cb){
   await fetch('/toggle?role='+encodeURIComponent(role)+'&on='+cb.checked);
   refresh();
 }
 async function refresh(){
   let s;
   try { s = await (await fetch('/state')).json(); } catch(e) { return; }
   for (const role in roles){
     const cb = document.querySelector('input[data-role="'+role+'"]');
     if (cb) { cb.checked = s.granted.includes(roles[role]); cb.disabled = !s.synced; }
   }
   document.getElementById('status').textContent = s.synced
     ? 'Authorized by the engine: '+s.count+' publisher(s)'+(s.count ? ' — '+s.granted.join(', ') : '')
     : "Waiting for the engine's current rule set…";
 }
 refresh(); setInterval(refresh, 3000);
</script></body></html>''';
}

Future<void> main(List<String> args) async {
  final cli = await CLIBase.fromCommandLineArgs(args, namespace: kNamespace);
  atClient = cli.atClient;
  me = atClient.getCurrentAtSign()!;
  await _loadRoles();
  _watchEngine(); // the engine's next publish (immediate or heartbeat) fills the page

  final server = await HttpServer.bind(InternetAddress.loopbackIPv4, kPort);
  stdout.writeln('[policy-admin] $me serving http://127.0.0.1:$kPort  '
      '(profile=$profile, engine=$engineAtSign)');
  await for (final req in server) {
    if (req.uri.path == '/toggle') {
      final role = req.uri.queryParameters['role'];
      final on = req.uri.queryParameters['on'] == 'true';
      final at = roleToAtSign[role];
      if (!synced) {
        // Pushing now would send a set built from nothing and revoke everything else.
        req.response.statusCode = HttpStatus.conflict;
        req.response.write(jsonEncode(
            {'error': "the engine's current rule set is not known yet"}));
        await req.response.close();
        continue;
      }
      if (at != null) {
        if (on) {
          granted.add(at);
        } else {
          granted.remove(at);
        }
        await _pushGrants();
      }
      req.response
        ..headers.contentType = ContentType.json
        ..write(jsonEncode({'count': granted.length, 'granted': granted.toList()}));
    } else if (req.uri.path == '/state') {
      req.response
        ..headers.contentType = ContentType.json
        ..write(jsonEncode({
          'count': granted.length,
          'granted': granted.toList(),
          'synced': synced,
          'roles': roleToAtSign,
        }));
    } else if (req.uri.path == '/') {
      req.response
        ..headers.contentType = ContentType.html
        ..write(_html());
    } else {
      req.response.statusCode = 404;
    }
    await req.response.close();
  }
}
