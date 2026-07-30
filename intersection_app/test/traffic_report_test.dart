// Copyright (C) 2026 / Atsign migration
// SPDX-License-Identifier: Apache-2.0
//
// Pins the report contract to dart_client/bin/change_route.dart, which is verified
// end-to-end against the planner. If these drift, the phone's reports would be
// delivered but not understood.
import 'dart:convert';

import 'package:at_client/at_client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intersection_app/car_counter.dart';
import 'package:intersection_app/vehicle_detector.dart';
import 'package:intersection_app/sensor_settings.dart';
import 'package:intersection_app/traffic_report.dart';

void main() {
  final reporter = TrafficReporter(_NullAtClient());
  const config = IntersectionConfig(plannerAtSign: '@alpha');

  group('payload contract', () {
    test('matches the fields the planner (Intel LiveTrafficData) parses', () {
      final payload = jsonDecode(reporter.buildPayload(config, 30)) as Map<String, dynamic>;
      expect(payload.keys.toSet(), {
        'location_coordinates',
        'intersection_name',
        'timestamp',
        'traffic_density',
        'traffic_description',
        'weather_status',
        'incident_status',
      });
      expect(payload['location_coordinates'], {'latitude': 37.54812, 'longitude': -122.0241});
      expect(payload['traffic_density'], 30);
      expect(payload['weather_status'], 'Clear');
    });

    test('incident_status flips above 12, as in change_route.dart', () {
      String status(int d) =>
          (jsonDecode(reporter.buildPayload(config, d)) as Map)['incident_status'] as String;
      expect(status(12), 'clear');
      expect(status(13), 'crowding');
    });

    test('timestamp is ISO-8601', () {
      final payload = jsonDecode(
          reporter.buildPayload(config, 1, now: DateTime.utc(2026, 7, 29, 12, 30))) as Map;
      expect(payload['timestamp'], '2026-07-29T12:30:00.000Z');
    });
  });

  group('key contract', () {
    test('live_traffic shared to the planner with a TTL', () {
      final key = reporter.buildKey(config, '@bravo');
      expect(key.key, 'live_traffic');
      expect(key.namespace, 'smartroute');
      expect(key.sharedBy, '@bravo');
      expect(key.sharedWith, '@alpha');
      expect(key.metadata.ttl, 60000);
    });
  });

  group('density mapping', () {
    test('a single recognised car already crosses the planner threshold', () {
      expect(reporter.densityFor(config, 0), 0);
      // one recognised car must already cross the planner's threshold of 10
      expect(reporter.densityFor(config, 1), 15);
      // and two match the density the proven CLI demo sends
      expect(reporter.densityFor(config, 2), 30);
      // the settings slider now reaches 50 per car
      expect(reporter.densityFor(config.copyWith(densityPerCar: 50), 3), 150);
    });
  });

  group('car counter', () {
    test('an unlabelled box still counts (ML Kit often returns boxes with no label)', () {
      // Regression: these arrived scored 0.0 and were filtered out, so several cars
      // in view counted as none.
      final counter = CarCounter(minConfidence: 0.30);
      expect(counter.countIn(const [
        Detection('Object', 1.0),
        Detection('Object', 1.0),
        Detection('Object', 1.0),
      ]), 3);
    });

    test('filters by confidence', () {
      final counter = CarCounter(minConfidence: 0.5);
      expect(counter.countIn([const Detection('Object', 0.9), const Detection('Object', 0.2)]), 1);
    });

    test('vehicle-label filter is opt-in', () {
      final detections = [const Detection('Home good', 0.9), const Detection('car', 0.9)];
      expect(CarCounter().countIn(detections), 2);
      expect(CarCounter(requireVehicleLabel: true).countIn(detections), 1);
    });

    test('reports the maximum within the window, then decays to zero', () {
      final counter = CarCounter(window: const Duration(seconds: 2));
      final t0 = DateTime.utc(2026, 1, 1);
      counter.addFrame([const Detection('Object', 0.9), const Detection('Object', 0.9)], now: t0);
      counter.addFrame([const Detection('Object', 0.9)], now: t0.add(const Duration(seconds: 1)));
      // a brief drop-out must not lower the count inside the window
      expect(counter.smoothedCount(now: t0.add(const Duration(seconds: 1))), 2);
      // once the window passes with no frames, it falls back to zero
      expect(counter.smoothedCount(now: t0.add(const Duration(seconds: 5))), 0);
    });
  });

  group('settings persistence', () {
    test('round-trips every configured field', () {
      const original = SensorSettings(
        config: IntersectionConfig(
          plannerAtSign: '@intc_smartroute_planner',
          intersectionName: 'Desk demo',
          latitude: 37.7946,
          longitude: -122.3999,
          densityPerCar: 42,
        ),
        preset: 'Market St & 1st',
        intervalSeconds: 9,
        gateOnly: false,
        minConfidence: 0.55,
      );
      final restored = SensorSettings.decode(original.encode());
      expect(restored.config.plannerAtSign, '@intc_smartroute_planner');
      expect(restored.config.intersectionName, 'Desk demo');
      expect(restored.config.latitude, 37.7946);
      expect(restored.config.densityPerCar, 42);
      expect(restored.preset, 'Market St & 1st');
      expect(restored.intervalSeconds, 9);
      expect(restored.gateOnly, isFalse);
      expect(restored.minConfidence, 0.55);
    });

    test('absent or corrupt storage yields defaults, never a crash', () {
      for (final stored in [null, '', '   ', 'not json', '[]', '{"latitude":"nope"}']) {
        final settings = SensorSettings.decode(stored);
        expect(settings.config.plannerAtSign, const IntersectionConfig().plannerAtSign);
        expect(settings.config.latitude, const IntersectionConfig().latitude);
      }
    });

    test('a partial record keeps the stored fields and defaults the rest', () {
      final settings = SensorSettings.decode('{"plannerAtSign":"@alpha"}');
      expect(settings.config.plannerAtSign, '@alpha');
      expect(settings.config.densityPerCar, const IntersectionConfig().densityPerCar);
      expect(settings.gateOnly, isTrue);
    });
  });

  group('vehicle gate (ML Kit image labels)', () {
    test('recognises vehicle-ish labels above the confidence floor', () {
      expect(
          VehicleDetector.looksLikeVehicle(
              [const Detection('Vehicle', 0.81), const Detection('Sky', 0.9)], 0.5),
          isTrue);
      expect(VehicleDetector.looksLikeVehicle([const Detection('Toy', 0.7)], 0.5), isTrue);
    });

    test('ignores low-confidence vehicle labels', () {
      expect(VehicleDetector.looksLikeVehicle([const Detection('Car', 0.2)], 0.5), isFalse);
    });

    test('a desk of non-vehicles does not open the gate', () {
      expect(
          VehicleDetector.looksLikeVehicle(
              [const Detection('Mug', 0.95), const Detection('Table', 0.9)], 0.5),
          isFalse);
    });
  });
}

/// The reporter only touches the client inside send(); these tests never call it.
class _NullAtClient implements AtClient {
  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnsupportedError('no AtClient in unit tests');
}
