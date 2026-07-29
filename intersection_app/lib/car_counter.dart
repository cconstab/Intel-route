// Copyright (C) 2026 / Atsign migration
// SPDX-License-Identifier: Apache-2.0
//
// Turns a stream of per-frame detections into a stable vehicle count.
//
// Why smoothing: ML Kit's tracker drops and re-acquires objects between frames,
// so a raw per-frame count flickers (3, 2, 3, 1, 3...). We report the maximum
// seen in a short window, so a briefly occluded model car still counts — the
// same intent as a fixed camera counting vehicles at a junction.
//
// Flutter-free on purpose so it is unit-testable without a device.

/// One detected object from a frame, reduced to what we care about.
class Detection {
  final String label;
  final double confidence;
  const Detection(this.label, this.confidence);
}

/// Labels that indicate a vehicle, for detectors that classify specifically.
///
/// NOTE: ML Kit's *base* object detector only returns coarse categories
/// (e.g. "Home good", "Fashion good", "Unknown"), so it will rarely say "car"
/// for a model car. Label filtering is therefore OFF by default; it becomes
/// useful when a vehicle-aware model (e.g. a COCO/YOLO detector, which has a
/// real "car" class) is substituted.
const Set<String> kVehicleLabelHints = {
  'car', 'vehicle', 'truck', 'van', 'bus', 'motorcycle', 'toy vehicle', 'wheel',
};

class CarCounter {
  /// Ignore detections below this confidence.
  double minConfidence;

  /// Require a vehicle-ish label (see [kVehicleLabelHints]).
  bool requireVehicleLabel;

  /// How long a frame's count keeps contributing to the reported maximum.
  Duration window;

  final List<_Sample> _samples = [];

  CarCounter({
    this.minConfidence = 0.30,
    this.requireVehicleLabel = false,
    this.window = const Duration(seconds: 2),
  });

  /// Number of vehicles in one frame, after filtering.
  int countIn(List<Detection> detections) {
    return detections.where((d) {
      if (d.confidence < minConfidence) return false;
      if (!requireVehicleLabel) return true;
      final label = d.label.toLowerCase();
      return kVehicleLabelHints.any(label.contains);
    }).length;
  }

  /// Record one frame's detections.
  void addFrame(List<Detection> detections, {DateTime? now}) {
    final at = now ?? DateTime.now();
    _samples.add(_Sample(at, countIn(detections)));
    _prune(at);
  }

  /// The reported count: the maximum within the window (0 once it goes quiet).
  int smoothedCount({DateTime? now}) {
    _prune(now ?? DateTime.now());
    if (_samples.isEmpty) return 0;
    return _samples.map((s) => s.count).reduce((a, b) => a > b ? a : b);
  }

  void reset() => _samples.clear();

  void _prune(DateTime now) {
    _samples.removeWhere((s) => now.difference(s.at) > window);
  }
}

class _Sample {
  final DateTime at;
  final int count;
  const _Sample(this.at, this.count);
}
