// Cross-language interop spike — Dart subscriber.
// Receives notifications (from Python atsdk or Dart) and prints the decrypted value.
// Run (keys in $HOME/.atsign/keys):
//   dart run bin/dart_subscriber.dart --atsign @bravo --root-domain vip.ve.atsign.zone -v
import 'dart:io';
import 'package:at_cli_commons/at_cli_commons.dart';

Future<void> main(List<String> args) async {
  final cli = await CLIBase.fromCommandLineArgs(args, namespace: 'smartroute');
  final atClient = cli.atClient;
  stdout.writeln('[dart-sub] authenticated as ${atClient.getCurrentAtSign()}');

  atClient.notificationService
      .subscribe(regex: 'smartroute', shouldDecrypt: true)
      .listen(
        (n) => stdout.writeln(
            '[dart-sub] OK  from=${n.from}  key=${n.key}\n             value=${n.value}'),
        onError: (e) => stderr.writeln('[dart-sub] ERR $e'),
      );

  stdout.writeln('[dart-sub] subscribed to regex "smartroute"; waiting...');
  await Future.delayed(const Duration(minutes: 5));
  exit(0);
}
