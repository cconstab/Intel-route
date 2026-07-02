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
final Set<String> granted = {};               // currently-authorized atSigns

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
  granted.addAll(roleToAtSign.values); // default: all publishers granted
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
        '<td><label class="sw"><input type="checkbox" ${on ? 'checked' : ''} '
        'onchange="toggle(\'$role\', this)"><span></span></label></td></tr>';
  }).join();
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
 <div id="status">Authorized: ${granted.length} publisher(s)</div>
 <div class="who">Toggle a publisher to grant/revoke. The planner enforces this within seconds;
   revoked publishers are dropped (default-deny).</div>
<script>
 async function toggle(role, cb){
   const r = await fetch('/toggle?role='+encodeURIComponent(role)+'&on='+cb.checked);
   const j = await r.json();
   document.getElementById('status').textContent = 'Authorized: '+j.count+' publisher(s) — '+j.granted.join(', ');
 }
</script></body></html>''';
}

Future<void> main(List<String> args) async {
  final cli = await CLIBase.fromCommandLineArgs(args, namespace: kNamespace);
  atClient = cli.atClient;
  me = atClient.getCurrentAtSign()!;
  await _loadRoles();
  await _pushGrants(); // publish initial state

  final server = await HttpServer.bind(InternetAddress.loopbackIPv4, kPort);
  stdout.writeln('[policy-admin] $me serving http://127.0.0.1:$kPort  '
      '(profile=$profile, engine=$engineAtSign)');
  await for (final req in server) {
    if (req.uri.path == '/toggle') {
      final role = req.uri.queryParameters['role'];
      final on = req.uri.queryParameters['on'] == 'true';
      final at = roleToAtSign[role];
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
