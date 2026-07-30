// Copyright (C) 2026 / Atsign migration
// SPDX-License-Identifier: Apache-2.0
//
// Everything the operator configures, as one serialisable value.
//
// Flutter-free so the encoding is unit-testable; the atSign I/O lives in
// settings_store.dart.
import 'dart:convert';

import 'traffic_report.dart';

class SensorSettings {
  final IntersectionConfig config;

  /// Which entry of [kRoutePresets] the location came from, so the picker can
  /// restore the same selection (the coordinates live in [config]).
  final String preset;

  final int intervalSeconds;

  /// Only count objects while the labeler recognises a vehicle.
  final bool gateOnly;

  /// Minimum confidence for a detection to count.
  final double minConfidence;

  const SensorSettings({
    this.config = const IntersectionConfig(),
    this.preset = 'berkeley-oakland-i880 (midpoint — proven)',
    this.intervalSeconds = 5,
    this.gateOnly = true,
    this.minConfidence = 0.30,
  });

  Map<String, dynamic> toJson() => {
        'plannerAtSign': config.plannerAtSign,
        'intersectionName': config.intersectionName,
        'latitude': config.latitude,
        'longitude': config.longitude,
        'densityPerCar': config.densityPerCar,
        'ttlMillis': config.ttlMillis,
        'preset': preset,
        'intervalSeconds': intervalSeconds,
        'gateOnly': gateOnly,
        'minConfidence': minConfidence,
      };

  String encode() => jsonEncode(toJson());

  /// Rebuild from stored JSON. Anything missing or malformed falls back to the
  /// default for that field rather than losing the whole configuration.
  static SensorSettings fromJson(Map<String, dynamic> json) {
    const fallback = SensorSettings();
    T pick<T>(String key, T defaultValue) {
      final value = json[key];
      return value is T ? value : defaultValue;
    }

    // ints/doubles arrive from JSON as num
    double number(String key, double defaultValue) {
      final value = json[key];
      return value is num ? value.toDouble() : defaultValue;
    }

    int integer(String key, int defaultValue) {
      final value = json[key];
      return value is num ? value.toInt() : defaultValue;
    }

    return SensorSettings(
      config: IntersectionConfig(
        plannerAtSign: pick('plannerAtSign', fallback.config.plannerAtSign),
        intersectionName: pick('intersectionName', fallback.config.intersectionName),
        latitude: number('latitude', fallback.config.latitude),
        longitude: number('longitude', fallback.config.longitude),
        densityPerCar: integer('densityPerCar', fallback.config.densityPerCar),
        ttlMillis: integer('ttlMillis', fallback.config.ttlMillis),
      ),
      preset: pick('preset', fallback.preset),
      intervalSeconds: integer('intervalSeconds', fallback.intervalSeconds),
      gateOnly: pick('gateOnly', fallback.gateOnly),
      minConfidence: number('minConfidence', fallback.minConfidence),
    );
  }

  /// Decode stored text; returns defaults if it is absent or unreadable.
  static SensorSettings decode(String? text) {
    if (text == null || text.trim().isEmpty) return const SensorSettings();
    try {
      final decoded = jsonDecode(text);
      if (decoded is! Map<String, dynamic>) return const SensorSettings();
      return fromJson(decoded);
    } catch (_) {
      return const SensorSettings();
    }
  }
}
