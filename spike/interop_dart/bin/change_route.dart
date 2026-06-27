// Pure-Dart route changer — the Dart twin of scripts/trigger_incident.py.
//
// Publishes a live_traffic record (as an intersection atSign, e.g. @bravo) to the
// planner. High density (>10) blocks the current shortest route, so the planner
// reroutes; low density clears it. Proves Dart can DRIVE the system, not just
// receive from it. Same encrypted wire contract as the Python publishers.
//
// Run (keys in $HOME/.atsign/keys):
//   dart run bin/change_route.dart --atsign @bravo --root-domain vip.ve.atsign.zone
//   dart run bin/change_route.dart --atsign @bravo --root-domain vip.ve.atsign.zone --density 0   # clear
import 'dart:convert';
import 'dart:io';

import 'package:at_client/at_client.dart';
import 'package:at_cli_commons/at_cli_commons.dart';

Future<void> main(List<String> args) async {
  final parser = CLIBase.createArgsParser(namespace: 'smartroute')
    ..addOption('to', defaultsTo: '@alpha', help: 'planner atSign')
    ..addOption('lat', defaultsTo: '37.54812', help: 'incident latitude (a trackpoint on the shortest route)')
    ..addOption('lon', defaultsTo: '-122.0241', help: 'incident longitude')
    ..addOption('density', defaultsTo: '30', help: 'vehicle density: >10 reroutes, <=10 clears')
    ..addOption('name', defaultsTo: 'Incident (Dart)', help: 'intersection name (its own cache key)');

  final cli = await CLIBase.fromCommandLineArgs(args, parser: parser, namespace: 'smartroute');
  final atClient = cli.atClient;
  final me = atClient.getCurrentAtSign()!;
  final a = parser.parse(args);
  final to = a['to'] as String;
  final density = int.parse(a['density'] as String);

  final key = AtKey()
    ..key = 'live_traffic'
    ..namespace = 'smartroute'
    ..sharedBy = me
    ..sharedWith = to
    ..metadata = (Metadata()..ttl = 60000);

  final payload = jsonEncode({
    'location_coordinates': {
      'latitude': double.parse(a['lat'] as String),
      'longitude': double.parse(a['lon'] as String),
    },
    'intersection_name': a['name'],
    'timestamp': DateTime.now().toIso8601String(),
    'traffic_density': density,
    'traffic_description': 'set by Dart change_route',
    'weather_status': 'Clear',
    'incident_status': density > 12 ? 'crowding' : 'clear',
  });

  stdout.writeln('[change_route] $me -> $to  density=$density at (${a['lat']}, ${a['lon']})');
  final res = await atClient.notificationService
      .notify(NotificationParams.forUpdate(key, value: payload));
  stdout.writeln('[change_route] status=${res.notificationStatusEnum}');
  stdout.writeln(density > 10
      ? '   planner should reroute within ~8s (auto-clears after ~60s TTL).'
      : '   low density — planner stays on / returns to the shortest route.');
  exit(0);
}
