// Copyright (C) 2026 / Atsign migration
// SPDX-License-Identifier: Apache-2.0
//
// Smart Route Planning — commuter app (Atsign Platform).
// Receives the planner's pushed optimal route + reroute alerts and renders them
// on a map; sends start/destination requests. Identity = the user's own atSign.
//
// NOTE for the local ephemeral environment: set rootDomain to vip.ve.atsign.zone
// (AtAuthRequest uses AtRootDomain; the prod flow shown here uses atsignDomain).
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:at_client_flutter/at_client_flutter.dart';
import 'package:at_auth/at_auth.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:path_provider/path_provider.dart';

const String kNamespace = 'smartroute';
const String kPlannerAtSign = '@smartroute_planner'; // EE: @alpha

// Root servers offered in the sign-in dialog (production + local test environment).
final Map<String, AtRootDomain> kRootDomains = {
  'root.atsign.org (production)': AtRootDomain.atsignDomain,
  'vip.ve.atsign.zone:64 (test env)': const AtRootDomain('vip.ve.atsign.zone', 64),
};

void main() => runApp(const CommuterApp());

class CommuterApp extends StatelessWidget {
  const CommuterApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Smart Route — Commuter',
      theme: ThemeData(colorSchemeSeed: Colors.green, useMaterial3: true),
      home: const AuthScreen(),
    );
  }
}

/// Sign-in screen — pick an atSign AND the root server (production or test env),
/// then authenticate from the device keychain or a `.atKeys` file.
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
      Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const HomePage()));
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

    // atSign + root-server picker (defaults shown; user can type a custom domain).
    final req = await AtSignSelectionDialog.show(
      context,
      existingAtSigns: existing,
      existingDomains: kRootDomains,
    );
    if (req == null || !context.mounted) return;
    final atSign = req.atSign;
    final rootDomain = req.rootDomain;

    // Use device keychain if we already hold this atSign's keys; otherwise load an .atKeys file.
    if (existing.contains(atSign)) {
      await _finish(context, AtAuthRequest(atSign, atKeysIo: KeychainAtKeysIo(), rootDomain: rootDomain));
    } else {
      final fileIo = await AtKeysFileDialog.show(context);
      if (fileIo == null || !context.mounted) return;
      await _finish(context, AtAuthRequest(atSign, atKeysIo: fileIo, rootDomain: rootDomain));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Smart Route — Commuter')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 360),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.alt_route, size: 64, color: Colors.green),
              const SizedBox(height: 16),
              const Text('Sign in with your Atsign',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              const Text('Choose your atSign and root server to continue.',
                  textAlign: TextAlign.center),
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
    );
  }
}

/// Home — request a route, watch it update live with reroute alerts on a map.
class HomePage extends StatefulWidget {
  const HomePage({super.key});
  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final _locations = const ['Berkeley, California', 'Santa Clara, California'];
  String _from = 'Berkeley, California';
  String _to = 'Santa Clara, California';

  List<LatLng> _points = [];
  String _banner = 'Pick start & destination, then Find Route.';
  bool _rerouted = false;

  late final AtClient _atClient;

  @override
  void initState() {
    super.initState();
    _atClient = AtClientManager.getInstance().atClient;
    _atClient.notificationService
        .subscribe(regex: 'route.$kNamespace', shouldDecrypt: true)
        .listen(_onRoute);
  }

  void _onRoute(AtNotification n) {
    final value = n.value;
    if (value == null) return;
    final d = jsonDecode(value) as Map<String, dynamic>;
    setState(() {
      _rerouted = d['rerouted'] == true;
      final tag = _rerouted ? '🚨 Rerouted' : '🧭 Route';
      _banner =
          '$tag: ${d['route_name']} (${(d['distance_km'] as num).toStringAsFixed(1)} km) — ${d['reason']}';
      _points = [
        for (final p in (d['points'] as List))
          LatLng((p[0] as num).toDouble(), (p[1] as num).toDouble())
      ];
    });
  }

  Future<void> _findRoute() async {
    final key = AtKey()
      ..key = 'request'
      ..namespace = kNamespace
      ..sharedBy = _atClient.getCurrentAtSign()
      ..sharedWith = kPlannerAtSign
      ..metadata = (Metadata()..ttl = 60000);
    await _atClient.notificationService.notify(
      NotificationParams.forUpdate(key, value: jsonEncode({'source': _from, 'destination': _to})),
    );
    setState(() => _banner = 'Requested $_from → $_to … waiting for the planner.');
  }

  @override
  Widget build(BuildContext context) {
    final center =
        _points.isNotEmpty ? _points[_points.length ~/ 2] : const LatLng(37.7, -122.2);
    return Scaffold(
      appBar: AppBar(title: const Text('Smart Route — Commuter')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                Expanded(child: _dd(_from, (v) => setState(() => _from = v))),
                const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 8), child: Icon(Icons.arrow_forward)),
                Expanded(child: _dd(_to, (v) => setState(() => _to = v))),
                const SizedBox(width: 8),
                FilledButton(onPressed: _findRoute, child: const Text('Find Route')),
              ],
            ),
          ),
          Container(
            width: double.infinity,
            color: _rerouted ? Colors.red.shade100 : Colors.green.shade50,
            padding: const EdgeInsets.all(12),
            child: Text(_banner, style: const TextStyle(fontWeight: FontWeight.w600)),
          ),
          Expanded(
            child: FlutterMap(
              options: MapOptions(initialCenter: center, initialZoom: 9),
              children: [
                TileLayer(
                  urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                  userAgentPackageName: 'com.atsign.commuter_app',
                ),
                if (_points.isNotEmpty)
                  PolylineLayer(polylines: [
                    Polyline(points: _points, strokeWidth: 5, color: Colors.green)
                  ]),
                if (_points.isNotEmpty)
                  MarkerLayer(markers: [
                    Marker(
                        point: _points.first,
                        child: const Icon(Icons.trip_origin, color: Colors.blue)),
                    Marker(point: _points.last, child: const Icon(Icons.place, color: Colors.red)),
                  ]),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _dd(String value, ValueChanged<String> onChanged) => DropdownButton<String>(
        value: value,
        isExpanded: true,
        items: [for (final l in _locations) DropdownMenuItem(value: l, child: Text(l))],
        onChanged: (v) => onChanged(v ?? value),
      );
}
