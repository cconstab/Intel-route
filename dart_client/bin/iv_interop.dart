// Interop helper using the Dart reference at_client. Put/get self and shared keys
// so a Python peer (at_python fix/put-get-random-iv) can read/write them, proving
// the Python IV/ivNonce behavior is wire-compatible with Dart.
//
//   dart run bin/iv_interop.dart --atsign @alpha --root-domain vip.ve.atsign.zone \
//     --op put-shared --key demo --value hi --shared-with @bravo
import 'dart:io';

import 'package:at_client/at_client.dart';
import 'package:at_cli_commons/at_cli_commons.dart';

const String ns = 'itest';

/// Dart at_client is local-first: put writes locally then syncs to the server, and
/// get of self/own keys reads locally. For cross-SDK interop we must push after a
/// put and pull before a get, so wait until the client is in sync with the server.
Future<void> waitInSync(AtClient atClient, {int timeoutSec = 30}) async {
  final sync = atClient.syncService;
  for (var i = 0; i < timeoutSec; i++) {
    sync.sync();
    try {
      if (await sync.isInSync()) return;
    } catch (_) {}
    await Future.delayed(const Duration(seconds: 1));
  }
}

Future<void> main(List<String> args) async {
  final parser = CLIBase.createArgsParser(namespace: ns)
    ..addOption('op', mandatory: true)
    ..addOption('key', mandatory: true)
    ..addOption('value', defaultsTo: '')
    ..addOption('shared-with');
  final cli = await CLIBase.fromCommandLineArgs(args, parser: parser, namespace: ns);
  final atClient = cli.atClient;
  final me = atClient.getCurrentAtSign()!;
  final a = parser.parse(args);
  final op = a['op'] as String;
  final keyName = a['key'] as String;
  final value = a['value'] as String;
  final sw = a['shared-with'] as String?;

  switch (op) {
    case 'put-self':
      final k = AtKey()
        ..key = keyName
        ..namespace = ns
        ..sharedBy = me;
      await atClient.put(k, value);
      await waitInSync(atClient); // push to server
      stdout.writeln('OK');
      break;
    case 'get-self':
      await waitInSync(atClient); // pull peer's writes
      final k = AtKey()
        ..key = keyName
        ..namespace = ns
        ..sharedBy = me;
      final r = await atClient.get(k);
      stdout.writeln('VALUE:${r.value}');
      break;
    case 'put-shared':
      final k = AtKey()
        ..key = keyName
        ..namespace = ns
        ..sharedBy = me
        ..sharedWith = sw;
      await atClient.put(k, value);
      await waitInSync(atClient); // push to server
      stdout.writeln('OK');
      break;
    case 'get-shared':
      final k = AtKey()
        ..key = keyName
        ..namespace = ns
        ..sharedBy = sw
        ..sharedWith = me;
      final r = await atClient.get(k);
      stdout.writeln('VALUE:${r.value}');
      break;
  }
  exit(0);
}
