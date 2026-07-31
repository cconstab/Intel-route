// Policy Admin — pure Dart, runs as the Policy Admin atSign (@route_policy_admin / @kilo)
// and exposes the access policy as a small web page.
//
// The engine owns the rule set; this page reflects it. It holds no opinion of its own: the
// engine mirrors its rules here and the page renders (and polls) that, so a change made
// elsewhere shows up without a reload. A toggle is a REQUEST — it is pushed to the engine,
// re-pushed if the engine has not mirrored it back (a notification can be lost), and then
// reported as not applied rather than silently springing the switch back. Nothing is pushed
// at startup: doing so would overwrite the operator's revocations every time this process
// restarted.
//
// Segregation of duties: the admin (@kilo) governs access from a different identity than the
// policy engine (@juliet) and the planner (@alpha).
//
// Run (keys in $HOME/.atsign/keys):
//   dart run bin/policy_admin.dart --atsign @kilo --root-domain vip.ve.atsign.zone
// then open http://127.0.0.1:8090
import 'dart:async';
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

// A toggle is a request, not a fact: it counts only once the engine mirrors it back. A
// notification can be lost, and the engine can reject a change (stale version) or fail to
// receive it at all, so an unconfirmed change is retried and then reported rather than
// silently reverting the switch under the operator.
Set<String>? wanted;        // the set we asked the engine for, until it confirms
DateTime? wantedSince;
int attempts = 0;
String? unappliedReport;   // why the last change did not take effect
String lastPushStatus = '';  // the atServer's verdict on our last push (delivered/…)

const int kMaxAttempts = 3;
const Duration kRetryAfter = Duration(seconds: 8);
const Duration kGiveUpAfter = Duration(seconds: 30);
// The engine republishes every 30s, so silence past this means something is wrong.
const Duration kExpectEngineWithin = Duration(seconds: 45);

final DateTime startedAt = DateTime.now();
int policyNotificationsSeen = 0;   // matched the engine
int otherNotificationsSeen = 0;    // arrived, but not from the engine we expect
String lastOtherSender = '';

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
    if (!notification.key.contains('policy')) return;
    // The sender check is what matters: only the engine may state the rule set. Compare
    // loosely on case and the leading '@' so a formatting difference cannot silently
    // reject every message and leave the page waiting forever.
    if (_normalise(notification.from) != _normalise(engineAtSign)) {
      otherNotificationsSeen++;
      lastOtherSender = notification.from;
      stdout.writeln('[policy-admin] ignoring a policy record from '
          '"${notification.from}" — this admin only accepts $engineAtSign');
      return;
    }
    policyNotificationsSeen++;
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
      if (!synced || _reportedStall) {
        stdout.writeln('[policy-admin] received the rule set from $engineAtSign');
        _reportedStall = false;
      }
      synced = true;
      if (changed) {
        stdout.writeln('[policy-admin] engine rule set is now '
            '${granted.length} publisher(s): ${granted.toList()..sort()}');
      }
      if (wanted != null && _sameSet(engineGrants, wanted!)) {
        stdout.writeln('[policy-admin] the engine applied the change');
        wanted = null;
        wantedSince = null;
        attempts = 0;
        unappliedReport = null;
      }
    } catch (e) {
      stdout.writeln('[policy-admin] unreadable policy from $engineAtSign: $e');
    }
  }, onError: (e) => stdout.writeln('[policy-admin] subscription error: $e'));
}

String _normalise(String atSign) => atSign.trim().toLowerCase().replaceFirst('@', '');

/// Say why the page is still empty. Silence here used to be indistinguishable from a
/// healthy but quiet system, so an operator had nothing to act on.
String? _notSyncedReport() {
  if (synced) return null;
  final waited = DateTime.now().difference(startedAt);
  if (waited < kExpectEngineWithin) return null;
  final seen = otherNotificationsSeen > 0
      ? ' A policy record did arrive, but from "$lastOtherSender" rather than '
          '$engineAtSign — check that both sides use the same ATSIGN_PROFILE.'
      : ' Nothing has arrived at all.';
  return 'No rule set from the policy engine $engineAtSign after ${waited.inSeconds}s '
      '(it publishes every 30s).$seen This admin is signed in as $me, and the engine '
      'mirrors its rules to the atSign configured as policy_admin — if that is not $me, '
      'no rule set will ever arrive here. Otherwise check that the policy engine is '
      'running: policy_engine.log ends with a FATAL line if it refused to start.';
}

bool _sameSet(Set<String> a, Set<String> b) =>
    a.length == b.length && a.containsAll(b);

bool _chasing = false;
bool _reportedStall = false;

/// Re-push an unconfirmed change, then report it if the engine never applies it. Without
/// this, a lost notification or a rejected change is indistinguishable from a UI glitch:
/// the switch just springs back with no explanation.
Future<void> _chaseUnconfirmed() async {
  final stalled = _notSyncedReport();
  if (stalled != null && !_reportedStall) {
    _reportedStall = true;
    stdout.writeln('[policy-admin] $stalled');
  }
  if (_chasing) return; // a push can outlast the timer tick; don't double-count attempts
  _chasing = true;
  try {
    await _chaseOnce();
  } finally {
    _chasing = false;
  }
}

Future<void> _chaseOnce() async {
  final desired = wanted;
  if (desired == null) return;
  if (_sameSet(granted, desired)) {
    wanted = null;
    attempts = 0;
    return;
  }
  final age = DateTime.now().difference(wantedSince!);
  if (age > kGiveUpAfter || attempts >= kMaxAttempts) {
    final missing = desired.difference(granted).toList()..sort();
    final extra = granted.difference(desired).toList()..sort();
    final delivered = lastPushStatus.toLowerCase() == 'delivered';
    unappliedReport = 'The engine did not apply this change after $attempts attempt(s). '
        'It still reports ${granted.length} authorized publisher(s)'
        '${missing.isNotEmpty ? "; not authorized: ${missing.join(", ")}" : ""}'
        '${extra.isNotEmpty ? "; still authorized: ${extra.join(", ")}" : ""}. '
        'The push was reported as "$lastPushStatus". '
        '${delivered ? "Delivered, so the engine has it and is not acting on it: look for "
            "an \"IGNORED admin change\" line in policy_engine.log (a rejected version), "
            "and if there is no line at all its listener is not consuming — restart the "
            "policy engine, whose rules are persisted, so nothing is lost."
            : "Not delivered, so it never reached the engine: check that $engineAtSign is "
              "the right engine atSign for this profile, that its atServer is reachable, "
              "and that this admin and the engine use the same root domain."}';
    stdout.writeln('[policy-admin] $unappliedReport');
    wanted = null;
    wantedSince = null;
    attempts = 0;
    return;
  }
  if (age > kRetryAfter * attempts) {
    attempts++;
    stdout.writeln('[policy-admin] the engine has not confirmed the change; '
        're-pushing (attempt $attempts of $kMaxAttempts)');
    await _pushGrants(desired);
  }
}

Future<void> _pushGrants(Set<String> grants) async {
  final key = AtKey()
    ..key = 'admin'
    ..namespace = kNamespace
    ..sharedBy = me
    ..sharedWith = engineAtSign
    ..metadata = (Metadata()..ttl = 86400000);
  final value = jsonEncode({
    'grants': grants.toList(),
    'version': DateTime.now().millisecondsSinceEpoch,  // engine ignores stale/replayed versions
  });
  final res = await atClient.notificationService
      .notify(NotificationParams.forUpdate(key, value: value));
  lastPushStatus = res.notificationStatusEnum.toString().split('.').last;
  stdout.writeln('[policy-admin] pushed ${grants.length} grants to $engineAtSign '
      '($lastPushStatus)');
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
 .warn{margin-top:14px;padding:12px 16px;background:#3a1f1f;border:1px solid #a33;
   border-radius:8px;color:#ffd7d7;max-width:720px;line-height:1.45}
 .pending{color:#ffd479}
</style></head><body>
 <h1>Route Policy Admin</h1>
 <div class="sub">Signed in as <b>$me</b> · changes pushed to engine <b>$engineAtSign</b> · default-deny</div>
 <table><tr><th>Role</th><th>atSign</th><th>Authorized</th></tr>$rows</table>
 <div id="status">Waiting for the engine's current rule set…</div>
 <div id="warn" class="warn" hidden></div>
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
   // While a change is in flight show what was asked for, so the switch does not spring
   // back and forth; once the engine confirms, its own set takes over.
   const shown = s.pending || s.granted;
   for (const role in roles){
     const cb = document.querySelector('input[data-role="'+role+'"]');
     if (cb) { cb.checked = shown.includes(roles[role]); cb.disabled = !s.synced; }
   }
   const status = document.getElementById('status');
   if (!s.synced) {
     status.textContent = "Waiting for the engine's current rule set…";
   } else if (s.pending) {
     status.className = 'pending';
     status.textContent = 'Applying… waiting for the engine to confirm (attempt '+s.attempts+')';
   } else {
     status.className = '';
     status.textContent = 'Authorized by the engine: '+s.count+' publisher(s)'+(s.count ? ' — '+s.granted.join(', ') : '');
   }
   const warn = document.getElementById('warn');
   warn.hidden = !s.unapplied;
   warn.textContent = s.unapplied || '';
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

  Timer.periodic(const Duration(seconds: 2), (_) => _chaseUnconfirmed());

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
        // Build the request from what the engine holds, so a toggle changes exactly one
        // publisher and cannot carry a stale view of the others.
        final desired = {...granted};
        on ? desired.add(at) : desired.remove(at);
        wanted = desired;
        wantedSince = DateTime.now();
        attempts = 1;
        unappliedReport = null;
        await _pushGrants(desired);
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
          'pending': wanted?.toList(),
          'attempts': attempts,
          'unapplied': unappliedReport ?? _notSyncedReport(),
          'lastPush': lastPushStatus,
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
