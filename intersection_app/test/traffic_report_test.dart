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
    test('cars are multiplied so a few model cars can cross the threshold of 10', () {
      expect(reporter.densityFor(config, 0), 0);
      expect(reporter.densityFor(config, 2), 12); // 2 cars x 6 -> reroute
      expect(reporter.densityFor(config, 1), 6); // 1 car -> below threshold
    });
  });

  group('car counter', () {
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
}

/// The reporter only touches the client inside send(); these tests never call it.
class _NullAtClient implements AtClient {
  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnsupportedError('no AtClient in unit tests');
}
