// Copyright (C) 2026 / Atsign migration
// SPDX-License-Identifier: Apache-2.0
//
// The sensor screen: on-device object detection over the camera, counted into a
// vehicle density, published to the planner as encrypted `live_traffic` records.
import 'dart:async';

import 'package:at_client/at_client.dart';
import 'package:at_client_flutter/at_client_flutter.dart';
import 'package:flutter/material.dart';
import 'package:camera/camera.dart';

import 'car_counter.dart';
import 'vehicle_detector.dart';
import 'traffic_report.dart';

class SensorPage extends StatefulWidget {
  const SensorPage({super.key});
  @override
  State<SensorPage> createState() => _SensorPageState();
}

class _SensorPageState extends State<SensorPage> {
  final CarCounter _counter = CarCounter();
  final VehicleDetector _detector = VehicleDetector();
  StreamSubscription<DetectionFrame>? _frameSub;
  bool _cameraReady = false;
  String _cameraError = '';
  bool _vehicleInView = false;
  bool _gateOnly = true;  // ignore counts when no vehicle is recognised in view
  late final TrafficReporter _reporter;
  late final String _me;

  IntersectionConfig _config = const IntersectionConfig();
  String _preset = kRoutePresets.keys.first;

  bool _reporting = false;
  int _intervalSeconds = 5;
  Timer? _timer;

  int _cars = 0;
  int _boxes = 0;  // raw detector boxes this frame, shown for diagnosis
  String _lastLabels = '';
  String _status = 'Starting…';
  bool _lastOk = false;
  int _sendOk = 0;
  int _sendFailed = 0;
  int _lastSentDensity = -1;
  DateTime _lastSendAt = DateTime.fromMillisecondsSinceEpoch(0);

  @override
  void initState() {
    super.initState();
    final atClient = AtClientManager.getInstance().atClient;
    _reporter = TrafficReporter(atClient);
    _me = atClient.getCurrentAtSign() ?? '(unknown)';
    _startCamera();
  }

  Future<void> _startCamera() async {
    try {
      await _detector.start();
      _frameSub = _detector.frames.listen(_onFrame);
      if (!mounted) return;
      setState(() => _cameraReady = true);
      // A sensor's job is to report, so arm it automatically — forgetting the switch
      // looked exactly like a broken pipeline. The switch remains, to pause.
      _toggleReporting(true);
    } catch (e) {
      if (mounted) setState(() => _cameraError = '$e');
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    _frameSub?.cancel();
    _detector.dispose();
    super.dispose();
  }

  // ---------------------------------------------------------------- detection
  void _onFrame(DetectionFrame frame) {
    // With the gate on, objects only count while the labeler recognises a vehicle —
    // so a desk full of mugs doesn't report congestion.
    final counted = (_gateOnly && !frame.vehicleInView) ? const <Detection>[] : frame.objects;
    _counter.addFrame(counted);
    var cars = _counter.smoothedCount();
    // The labeler looks at the whole frame and often recognises a vehicle that the box
    // detector misses (a small model car on a desk). Without this, the gate says
    // "vehicle recognised" while the count stays 0 and nothing is ever reported.
    if (cars == 0 && frame.vehicleInView) cars = 1;
    final labels = frame.frameLabels
        .take(3)
        .map((l) => '${l.label} ${(l.confidence * 100).round()}%')
        .join(', ');
    if (cars != _cars ||
        labels != _lastLabels ||
        frame.objects.length != _boxes ||
        frame.vehicleInView != _vehicleInView) {
      setState(() {
        _cars = cars;
        _boxes = frame.objects.length;
        _lastLabels = labels;
        _vehicleInView = frame.vehicleInView;
      });
      _maybeSendOnChange();
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

  /// Report a material change straight away rather than waiting for the next tick —
  /// a car appearing should move the map now. Throttled so a flickering count cannot
  /// spam the planner.
  void _maybeSendOnChange() {
    if (!_reporting) return;
    final density = _density;
    if (density == _lastSentDensity) return;
    final crossedThreshold = (density > 10) != (_lastSentDensity > 10);
    final movedALot = (density - _lastSentDensity).abs() >= 15;
    if (!crossedThreshold && !movedALot) return;
    if (DateTime.now().difference(_lastSendAt) < const Duration(seconds: 3)) return;
    _send(density);
  }

  Future<void> _send(int density) async {
    _lastSentDensity = density;
    _lastSendAt = DateTime.now();
    try {
      final NotificationResult result = await _reporter.send(_config, density);
      final ok = result.notificationStatusEnum == NotificationStatusEnum.delivered;
      if (!mounted) return;
      setState(() {
        _lastOk = ok;
        ok ? _sendOk++ : _sendFailed++;
        _status = 'density $density -> ${_config.plannerAtSign} '
            '(${result.notificationStatusEnum.name})';
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _lastOk = false;
        _sendFailed++;
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
                Positioned.fill(child: _preview()),
                Positioned(left: 12, top: 12, child: _readout()),
              ],
            ),
          ),
          _controls(),
        ],
      ),
    );
  }

  Widget _preview() {
    if (_cameraError.isNotEmpty) {
      return Container(
        color: Colors.black,
        alignment: Alignment.center,
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text('Camera unavailable:\n$_cameraError',
              textAlign: TextAlign.center, style: const TextStyle(color: Colors.white70)),
        ),
      );
    }
    final controller = _detector.controller;
    if (!_cameraReady || controller == null || !controller.value.isInitialized) {
      return Container(
        color: Colors.black,
        alignment: Alignment.center,
        child: const Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 12),
            Text('Starting camera…', style: TextStyle(color: Colors.white70)),
          ],
        ),
      );
    }
    return CameraPreview(controller);
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
          Text('detector boxes this frame: $_boxes',
              style: const TextStyle(color: Colors.white54, fontSize: 11)),
          Text('reported density: $_density',
              style: TextStyle(
                  color: rerouting ? Colors.orangeAccent : Colors.white70,
                  fontWeight: rerouting ? FontWeight.bold : FontWeight.normal)),
          Text(rerouting ? 'above planner threshold — expect reroute' : 'below threshold (10)',
              style: const TextStyle(color: Colors.white54, fontSize: 12)),
          Row(
            children: [
              Icon(_vehicleInView ? Icons.directions_car : Icons.no_transfer,
                  size: 14, color: _vehicleInView ? Colors.tealAccent : Colors.white38),
              const SizedBox(width: 4),
              Text(
                _vehicleInView
                    ? 'vehicle recognised in view'
                    : (_gateOnly ? 'no vehicle recognised — not counting' : 'gate off'),
                style: TextStyle(
                    color: _vehicleInView ? Colors.tealAccent : Colors.white38, fontSize: 11),
              ),
            ],
          ),
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
                Text('  ✓$_sendOk ✗$_sendFailed',
                    style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
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
        gateOnly: _gateOnly,
        onApply: (config, preset, interval, gateOnly) {
          setState(() {
            _config = config;
            _preset = preset;
            _intervalSeconds = interval;
            _gateOnly = gateOnly;
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
  final bool gateOnly;
  final void Function(IntersectionConfig, String, int, bool) onApply;

  const _SettingsSheet({
    required this.config,
    required this.preset,
    required this.intervalSeconds,
    required this.counter,
    required this.gateOnly,
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
  late bool _gateOnly;

  @override
  void initState() {
    super.initState();
    _planner = TextEditingController(text: widget.config.plannerAtSign);
    _name = TextEditingController(text: widget.config.intersectionName);
    _preset = widget.preset;
    _perCar = widget.config.densityPerCar;
    _interval = widget.intervalSeconds;
    _minConfidence = widget.counter.minConfidence;
    _gateOnly = widget.gateOnly;
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
            const SizedBox(height: 8),
            Text('Density per detected car: $_perCar'),
            const Text('cars x this = reported density (planner reroutes above 10)',
                style: TextStyle(fontSize: 11, color: Colors.grey)),
            Slider(
              value: _perCar.toDouble(),
              min: 1,
              max: 50,
              divisions: 49,
              label: '$_perCar',
              onChanged: (v) => setState(() => _perCar = v.round()),
            ),
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
              title: const Text('Only count when a vehicle is recognised'),
              subtitle: const Text(
                'The image labeler must see a vehicle-ish label (Car, Vehicle, Wheel, '
                "Toy...) before objects count. Turn off to count whatever is in view.",
                style: TextStyle(fontSize: 11),
              ),
              value: _gateOnly,
              onChanged: (v) => setState(() => _gateOnly = v),
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
                      _gateOnly,
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
