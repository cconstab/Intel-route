// Copyright (C) 2026 / Atsign migration
// SPDX-License-Identifier: Apache-2.0
//
// The sensor screen: on-device object detection over the camera, counted into a
// vehicle density, published to the planner as encrypted `live_traffic` records.
import 'dart:async';

import 'package:at_client/at_client.dart';
import 'package:at_client_flutter/at_client_flutter.dart';
import 'package:flutter/material.dart';
import 'package:flutter_smart_scanner/flutter_smart_scanner.dart';

import 'car_counter.dart';
import 'traffic_report.dart';

class SensorPage extends StatefulWidget {
  const SensorPage({super.key});
  @override
  State<SensorPage> createState() => _SensorPageState();
}

class _SensorPageState extends State<SensorPage> {
  final CarCounter _counter = CarCounter();
  late final TrafficReporter _reporter;
  late final String _me;

  IntersectionConfig _config = const IntersectionConfig();
  String _preset = kRoutePresets.keys.first;

  bool _reporting = false;
  int _intervalSeconds = 5;
  Timer? _timer;

  int _cars = 0;
  String _lastLabels = '';
  String _status = 'Not reporting yet.';
  bool _lastOk = false;

  @override
  void initState() {
    super.initState();
    final atClient = AtClientManager.getInstance().atClient;
    _reporter = TrafficReporter(atClient);
    _me = atClient.getCurrentAtSign() ?? '(unknown)';
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  // ---------------------------------------------------------------- detection
  void _onDetect(List<ScannerResult> results) {
    final objects = results.where((r) => r.mode == ScannerMode.object).toList();
    _counter.addFrame(
      objects.map((r) => Detection(r.content, r.confidence)).toList(),
    );
    final cars = _counter.smoothedCount();
    final labels = objects.isEmpty
        ? ''
        : objects.map((r) => '${r.content} ${(r.confidence * 100).round()}%').join(', ');
    if (cars != _cars || labels != _lastLabels) {
      setState(() {
        _cars = cars;
        _lastLabels = labels;
      });
    }
  }

  // ---------------------------------------------------------------- reporting
  int get _density => _reporter.densityFor(_config, _cars);

  void _toggleReporting(bool on) {
    setState(() => _reporting = on);
    _timer?.cancel();
    if (on) {
      _send(_density);
      _timer = Timer.periodic(Duration(seconds: _intervalSeconds), (_) => _send(_density));
    } else {
      setState(() => _status = 'Reporting paused (last report expires after its TTL).');
    }
  }

  Future<void> _send(int density) async {
    try {
      final NotificationResult result = await _reporter.send(_config, density);
      final ok = result.notificationStatusEnum == NotificationStatusEnum.delivered;
      if (!mounted) return;
      setState(() {
        _lastOk = ok;
        _status = 'density $density -> ${_config.plannerAtSign} '
            '(${result.notificationStatusEnum.name}) at ${TimeOfDay.now().format(context)}';
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _lastOk = false;
        _status = 'send failed: $e';
      });
    }
  }

  // --------------------------------------------------------------------- UI
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Intersection · $_me'),
        actions: [
          IconButton(
            icon: const Icon(Icons.tune),
            tooltip: 'Settings',
            onPressed: _openSettings,
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: Stack(
              children: [
                Positioned.fill(
                  child: SmartScanner(
                    onDetect: _onDetect,
                    accentColor: Colors.tealAccent,
                    showControls: false,
                  ),
                ),
                Positioned(left: 12, top: 12, child: _readout()),
              ],
            ),
          ),
          _controls(),
        ],
      ),
    );
  }

  Widget _readout() {
    final rerouting = _density > 10; // the planner's threshold
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.62),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('$_cars vehicles detected',
              style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
          Text('reported density: $_density',
              style: TextStyle(
                  color: rerouting ? Colors.orangeAccent : Colors.white70,
                  fontWeight: rerouting ? FontWeight.bold : FontWeight.normal)),
          Text(rerouting ? 'above planner threshold — expect reroute' : 'below threshold (10)',
              style: const TextStyle(color: Colors.white54, fontSize: 12)),
          if (_lastLabels.isNotEmpty)
            SizedBox(
              width: 240,
              child: Text(_lastLabels,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.white38, fontSize: 11)),
            ),
        ],
      ),
    );
  }

  Widget _controls() {
    return Card(
      margin: const EdgeInsets.all(10),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        child: Column(
          children: [
            Row(
              children: [
                Icon(_lastOk ? Icons.cloud_done : Icons.cloud_off,
                    size: 18, color: _lastOk ? Colors.green : Colors.grey),
                const SizedBox(width: 8),
                Expanded(child: Text(_status, style: const TextStyle(fontSize: 12))),
              ],
            ),
            const Divider(height: 12),
            Row(
              children: [
                Switch(value: _reporting, onChanged: _toggleReporting),
                Text(_reporting ? 'Reporting every ${_intervalSeconds}s' : 'Reporting off'),
                const Spacer(),
                TextButton.icon(
                  icon: const Icon(Icons.send, size: 18),
                  label: const Text('Send now'),
                  onPressed: () => _send(_density),
                ),
                TextButton.icon(
                  icon: const Icon(Icons.clear_all, size: 18),
                  label: const Text('Clear'),
                  onPressed: () => _send(0),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  void _openSettings() {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _SettingsSheet(
        config: _config,
        preset: _preset,
        intervalSeconds: _intervalSeconds,
        counter: _counter,
        onApply: (config, preset, interval) {
          setState(() {
            _config = config;
            _preset = preset;
            _intervalSeconds = interval;
          });
          if (_reporting) _toggleReporting(true); // restart the timer at the new interval
        },
      ),
    );
  }
}

/// Everything that makes the report land where the planner will act on it.
class _SettingsSheet extends StatefulWidget {
  final IntersectionConfig config;
  final String preset;
  final int intervalSeconds;
  final CarCounter counter;
  final void Function(IntersectionConfig, String, int) onApply;

  const _SettingsSheet({
    required this.config,
    required this.preset,
    required this.intervalSeconds,
    required this.counter,
    required this.onApply,
  });

  @override
  State<_SettingsSheet> createState() => _SettingsSheetState();
}

class _SettingsSheetState extends State<_SettingsSheet> {
  late TextEditingController _planner;
  late TextEditingController _name;
  late String _preset;
  late int _perCar;
  late int _interval;
  late double _minConfidence;
  late bool _requireLabel;

  @override
  void initState() {
    super.initState();
    _planner = TextEditingController(text: widget.config.plannerAtSign);
    _name = TextEditingController(text: widget.config.intersectionName);
    _preset = widget.preset;
    _perCar = widget.config.densityPerCar;
    _interval = widget.intervalSeconds;
    _minConfidence = widget.counter.minConfidence;
    _requireLabel = widget.counter.requireVehicleLabel;
  }

  @override
  void dispose() {
    _planner.dispose();
    _name.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 16, right: 16, top: 16,
        bottom: MediaQuery.of(context).viewInsets.bottom + 16,
      ),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Report settings',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            TextField(
              controller: _planner,
              decoration: const InputDecoration(
                labelText: 'Planner atSign',
                helperText: 'e.g. @alpha in the test env, or your production planner',
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _name,
              decoration: const InputDecoration(
                labelText: 'Intersection name',
                helperText: 'Its own slot in the planner cache',
              ),
            ),
            const SizedBox(height: 16),
            DropdownButtonFormField<String>(
              initialValue: _preset,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Location (must be on the route)'),
              items: kRoutePresets.keys
                  .map((k) => DropdownMenuItem(value: k, child: Text(k, overflow: TextOverflow.ellipsis)))
                  .toList(),
              onChanged: (v) => setState(() => _preset = v ?? _preset),
            ),
            const SizedBox(height: 8),
            const Text(
              'The planner only reroutes for congestion at a trackpoint of the route '
              'it is currently planning — a report elsewhere is delivered but ignored.',
              style: TextStyle(fontSize: 11, color: Colors.grey),
            ),
            const SizedBox(height: 16),
            _stepper('Density per detected car', _perCar, 1, 20,
                (v) => setState(() => _perCar = v),
                help: 'cars x this = reported density (planner reroutes above 10)'),
            _stepper('Report interval (seconds)', _interval, 2, 60,
                (v) => setState(() => _interval = v)),
            const SizedBox(height: 8),
            Text('Detection confidence: ${(_minConfidence * 100).round()}%'),
            Slider(
              value: _minConfidence,
              min: 0.1,
              max: 0.9,
              divisions: 8,
              label: '${(_minConfidence * 100).round()}%',
              onChanged: (v) => setState(() => _minConfidence = v),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Require a vehicle label'),
              subtitle: const Text(
                "Leave off with ML Kit's base model — it returns coarse categories "
                'and rarely labels a model car "car".',
                style: TextStyle(fontSize: 11),
              ),
              value: _requireLabel,
              onChanged: (v) => setState(() => _requireLabel = v),
            ),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Cancel'),
                ),
                const SizedBox(width: 8),
                FilledButton(
                  onPressed: () {
                    final coords = kRoutePresets[_preset]!;
                    widget.counter
                      ..minConfidence = _minConfidence
                      ..requireVehicleLabel = _requireLabel
                      ..reset();
                    widget.onApply(
                      widget.config.copyWith(
                        plannerAtSign: _planner.text.trim(),
                        intersectionName: _name.text.trim(),
                        latitude: coords[0],
                        longitude: coords[1],
                        densityPerCar: _perCar,
                      ),
                      _preset,
                      _interval,
                    );
                    Navigator.pop(context);
                  },
                  child: const Text('Apply'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _stepper(String label, int value, int min, int max, void Function(int) onChanged,
      {String? help}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label),
                if (help != null)
                  Text(help, style: const TextStyle(fontSize: 11, color: Colors.grey)),
              ],
            ),
          ),
          IconButton(
            icon: const Icon(Icons.remove_circle_outline),
            onPressed: value > min ? () => onChanged(value - 1) : null,
          ),
          Text('$value', style: const TextStyle(fontWeight: FontWeight.bold)),
          IconButton(
            icon: const Icon(Icons.add_circle_outline),
            onPressed: value < max ? () => onChanged(value + 1) : null,
          ),
        ],
      ),
    );
  }
}
