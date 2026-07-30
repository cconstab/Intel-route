// Copyright (C) 2026 / Atsign migration
// SPDX-License-Identifier: Apache-2.0
//
// Camera → ML Kit pipeline, owned by us rather than hidden inside a widget, because
// counting alone is not enough: we also need to know whether what is in view is
// actually a vehicle, and that requires access to the frames.
//
// Two ML Kit models run on each sampled frame:
//   * the object detector (stream mode, multiple objects, tracking) gives the BOXES —
//     the count that becomes traffic density;
//   * the image labeler gives SEMANTIC labels for the frame. Its base model knows
//     "Vehicle", "Car", "Toy" and hundreds more, which the object detector's coarse
//     categories ("Home good", "Unknown") never provide. It is used as a gate: are we
//     looking at cars at all?
//
// Neither needs a bundled model, so there is nothing to license or ship. See the
// README for the per-object custom-model upgrade, which this pipeline makes possible.
import 'dart:async';
import 'dart:io' show Platform;
import 'dart:ui' show Size;

import 'package:camera/camera.dart';
import 'package:google_mlkit_image_labeling/google_mlkit_image_labeling.dart';
import 'package:google_mlkit_object_detection/google_mlkit_object_detection.dart';

import 'car_counter.dart';

/// Labels from ML Kit's image labeler that mean "there is a vehicle in view".
/// The labeler reports things like "Vehicle", "Car", "Wheel", "Toy" for a model car.
const Set<String> kVehicleFrameLabels = {
  'vehicle', 'car', 'truck', 'van', 'bus', 'motorcycle', 'wheel', 'tire',
  'toy', 'model car', 'automotive',
};

/// One processed frame.
class DetectionFrame {
  /// Detected objects (the count that becomes density).
  final List<Detection> objects;

  /// True when the frame's labels look vehicle-ish.
  final bool vehicleInView;

  /// What the labeler actually saw, best first — shown in the UI so the operator can
  /// see why it is or isn't counting.
  final List<Detection> frameLabels;

  const DetectionFrame({
    required this.objects,
    required this.vehicleInView,
    required this.frameLabels,
  });

  static const empty = DetectionFrame(objects: [], vehicleInView: false, frameLabels: []);
}

class VehicleDetector {
  final _frames = StreamController<DetectionFrame>.broadcast();

  /// Processed frames. Never closed until [dispose].
  Stream<DetectionFrame> get frames => _frames.stream;

  CameraController? _camera;
  ObjectDetector? _objects;
  ImageLabeler? _labeler;

  bool _busy = false;
  int _frameIndex = 0;

  /// Only every Nth camera frame is analysed — inference is far slower than the
  /// preview, and dropping frames keeps the UI smooth.
  final int sampleEveryNthFrame;

  /// Minimum confidence for a frame label to count towards the vehicle gate.
  final double labelConfidence;

  VehicleDetector({this.sampleEveryNthFrame = 6, this.labelConfidence = 0.5});

  CameraController? get controller => _camera;

  Future<void> start() async {
    final cameras = await availableCameras();
    if (cameras.isEmpty) {
      throw StateError('no camera available on this device');
    }
    final back = cameras.firstWhere(
      (c) => c.lensDirection == CameraLensDirection.back,
      orElse: () => cameras.first,
    );

    _objects = ObjectDetector(
      options: ObjectDetectorOptions(
        // Stream mode is optimised for tracking a single prominent object and
        // under-reports a group; single-image mode enumerates them properly. We
        // sample frames and skip while busy, so the added latency is fine.
        mode: DetectionMode.single,
        classifyObjects: true,
        multipleObjects: true,
      ),
    );
    _labeler = ImageLabeler(options: ImageLabelerOptions(confidenceThreshold: 0.4));

    // NV21 on Android / BGRA on iOS give a single plane, which is what ML Kit's
    // InputImage.fromBytes expects — avoiding manual YUV conversion.
    _camera = CameraController(
      back,
      ResolutionPreset.medium,
      enableAudio: false,
      imageFormatGroup:
          Platform.isAndroid ? ImageFormatGroup.nv21 : ImageFormatGroup.bgra8888,
    );
    await _camera!.initialize();
    await _camera!.startImageStream(_onCameraFrame);
  }

  Future<void> _onCameraFrame(CameraImage image) async {
    if (_busy) return; // still analysing the previous frame
    if (_frameIndex++ % sampleEveryNthFrame != 0) return;
    final input = _toInputImage(image);
    if (input == null) return;

    _busy = true;
    try {
      final detected = await _objects?.processImage(input) ?? const [];
      final labels = await _labeler?.processImage(input) ?? const [];

      // A detected box counts even when ML Kit cannot classify it — it frequently
      // returns unlabelled boxes. Scoring those 0.0 made the confidence filter drop
      // every one of them, so several cars in view counted as none.
      final objects = detected
          .map((o) => o.labels.isEmpty
              ? const Detection('Object', 1.0)
              : Detection(o.labels.first.text, o.labels.first.confidence))
          .toList();
      final frameLabels = labels
          .map((l) => Detection(l.label, l.confidence))
          .toList()
        ..sort((a, b) => b.confidence.compareTo(a.confidence));

      _frames.add(DetectionFrame(
        objects: objects,
        vehicleInView: looksLikeVehicle(frameLabels, labelConfidence),
        frameLabels: frameLabels,
      ));
    } catch (_) {
      // A single bad frame must not kill the stream; the next one is along shortly.
    } finally {
      _busy = false;
    }
  }

  /// True when any sufficiently confident frame label names a vehicle.
  /// Pure so it can be unit-tested without a camera.
  static bool looksLikeVehicle(List<Detection> frameLabels, double minConfidence) {
    for (final label in frameLabels) {
      if (label.confidence < minConfidence) continue;
      final text = label.label.toLowerCase();
      if (kVehicleFrameLabels.any(text.contains)) return true;
    }
    return false;
  }

  InputImage? _toInputImage(CameraImage image) {
    final camera = _camera;
    if (camera == null || image.planes.isEmpty) return null;
    final rotation =
        InputImageRotationValue.fromRawValue(camera.description.sensorOrientation);
    final format = InputImageFormatValue.fromRawValue(image.format.raw);
    if (rotation == null || format == null) return null;
    final plane = image.planes.first;
    return InputImage.fromBytes(
      bytes: plane.bytes,
      metadata: InputImageMetadata(
        size: Size(image.width.toDouble(), image.height.toDouble()),
        rotation: rotation,
        format: format,
        bytesPerRow: plane.bytesPerRow,
      ),
    );
  }

  Future<void> dispose() async {
    try {
      await _camera?.stopImageStream();
    } catch (_) {
      // already stopped
    }
    await _camera?.dispose();
    await _objects?.close();
    await _labeler?.close();
    await _frames.close();
  }
}
