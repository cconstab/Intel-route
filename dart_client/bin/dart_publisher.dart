// Cross-language interop spike — Dart publisher.
// Sends a LiveTrafficData-shaped notification to a target atSign (default @alpha).
// Run (keys in $HOME/.atsign/keys):
//   dart run bin/dart_publisher.dart --atsign @bravo --root-domain vip.ve.atsign.zone --to @alpha -v
import 'dart:convert';
import 'dart:io';
import 'package:at_client/at_client.dart';
import 'package:at_cli_commons/at_cli_commons.dart';

Future<void> main(List<String> args) async {
  final parser = CLIBase.createArgsParser(namespace: 'smartroute')
    ..addOption('to', help: 'recipient atSign', defaultsTo: '@alpha');
  final cli = await CLIBase.fromCommandLineArgs(args, parser: parser, namespace: 'smartroute');
  final atClient = cli.atClient;
  final me = atClient.getCurrentAtSign()!;
  final to = parser.parse(args)['to'] as String;

  final key = AtKey()
    ..key = 'live_traffic'
    ..namespace = 'smartroute'
    ..sharedBy = me
    ..sharedWith = to
    ..metadata = (Metadata()..ttl = 60000);

  final payload = jsonEncode({
    'location_coordinates': {'latitude': 37.7946, 'longitude': -122.3999},
    'intersection_name': 'Market St & 1st (from Dart)',
    'timestamp': DateTime.now().toIso8601String(),
    'traffic_density': 17,
    'traffic_description': 'sent by Dart at_client',
    'weather_status': 'Clear',
    'incident_status': 'crowding',
  });

  stdout.writeln('[dart-pub] $me -> $to  notifying live_traffic.smartroute');
  final res = await atClient.notificationService
      .notify(NotificationParams.forUpdate(key, value: payload));
  stdout.writeln('[dart-pub] status=${res.notificationStatusEnum} '
      'exception=${res.atClientException}');
  exit(0);
}
