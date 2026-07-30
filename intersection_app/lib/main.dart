// Copyright (C) 2026 / Atsign migration
// SPDX-License-Identifier: Apache-2.0
//
// Smart Route Planning — intersection sensor app (Atsign Platform).
//
// The phone becomes a traffic intersection: it detects model cars with the
// on-device camera and publishes `live_traffic.smartroute` reports to the planner
// as its own atSign — the same encrypted, port-less record the CLI tool and the
// Python publishers send. Nothing listens on this device.
import 'package:at_auth/at_auth.dart';
import 'package:at_client_flutter/at_client_flutter.dart';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';

import 'sensor_page.dart';

const String kNamespace = 'smartroute';

// Root servers offered in the sign-in dialog (production + local test environment).
final Map<String, AtRootDomain> kRootDomains = {
  'root.atsign.org (production)': AtRootDomain.atsignDomain,
  'vip.ve.atsign.zone:64 (test env)': const AtRootDomain('vip.ve.atsign.zone', 64),
};

void main() => runApp(const IntersectionApp());

class IntersectionApp extends StatelessWidget {
  const IntersectionApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Smart Route — Intersection',
      theme: ThemeData(colorSchemeSeed: Colors.teal, useMaterial3: true),
      home: const AuthScreen(),
    );
  }
}

/// Sign-in — pick the intersection's atSign AND the root server, then
/// authenticate from the device keychain or a `.atKeys` file.
class AuthScreen extends StatelessWidget {
  const AuthScreen({super.key});

  Future<void> _afterAuth(BuildContext context, AtAuthRequest req, AuthResponse resp) async {
    final dir = await getApplicationSupportDirectory();
    final prefs = AtClientPreference()
      ..rootDomain = req.rootDomain.rootDomain
      ..rootPort = req.rootDomain.rootPort
      ..namespace = kNamespace
      ..commitLogPath = dir.path
      ..hiveStoragePath = dir.path;
    await AtClientManager.getInstance().setCurrentAtSign(
      resp.atSign, kNamespace, prefs,
      enrollmentId: resp.enrollmentId, atChops: resp.atChops, atLookUp: resp.atLookUp,
    );
    if (context.mounted) {
      Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const SensorPage()));
    }
  }

  Future<void> _finish(BuildContext context, AtAuthRequest authReq) async {
    final resp = await PkamDialog.show(context, request: authReq, backupKeys: [KeychainAtKeysIo()]);
    if (resp != null && resp.isSuccessful && context.mounted) {
      await _afterAuth(context, authReq, resp);
    }
  }

  Future<void> _signIn(BuildContext context) async {
    final existing = await KeychainStorage().getAllAtsigns();
    if (!context.mounted) return;

    final req = await AtSignSelectionDialog.show(
      context,
      existingAtSigns: existing,
      existingDomains: kRootDomains,
    );
    if (req == null || !context.mounted) return;

    if (existing.contains(req.atSign)) {
      await _finish(context,
          AtAuthRequest(req.atSign, atKeysIo: KeychainAtKeysIo(), rootDomain: req.rootDomain));
    } else {
      final fileIo = await AtKeysFileDialog.show(context);
      if (fileIo == null || !context.mounted) return;
      await _finish(context,
          AtAuthRequest(req.atSign, atKeysIo: fileIo, rootDomain: req.rootDomain));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Smart Route — Intersection')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 380),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.videocam, size: 64, color: Colors.teal),
                const SizedBox(height: 16),
                const Text('Intersection sensor',
                    style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                const Text(
                  'Sign in with the atSign that represents this intersection. '
                  'The camera counts model cars and reports encrypted traffic '
                  'density to the route planner.',
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 24),
                FilledButton.icon(
                  icon: const Icon(Icons.login),
                  label: const Text('Sign in'),
                  onPressed: () => _signIn(context),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
