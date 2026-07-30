// Copyright (C) 2026 / Atsign migration
// SPDX-License-Identifier: Apache-2.0
//
// Settings live in the atSign's own keystore as a SELF key: encrypted with the
// atSign's own key, and synced to its atServer. So the configuration follows the
// identity — reinstall the app or move to another handset, sign in, and the planner
// atSign, location and thresholds are already there. Nothing is stored in the clear
// and nothing extra is exposed: a self key is readable only by its owner.
import 'package:at_client/at_client.dart';

import 'sensor_settings.dart';

class SettingsStore {
  final AtClient atClient;
  final String namespace;

  SettingsStore(this.atClient, {this.namespace = 'smartroute'});

  /// A self key: shared by us, with no `sharedWith`, so only this atSign can read it.
  AtKey _key() => AtKey()
    ..key = 'sensor_settings'
    ..namespace = namespace
    ..sharedBy = atClient.getCurrentAtSign();

  /// Load saved settings, or defaults when none are stored yet (first run, or a
  /// fresh install whose sync has not caught up).
  Future<SensorSettings> load() async {
    try {
      final value = await atClient.get(_key());
      return SensorSettings.decode(value.value as String?);
    } catch (_) {
      return const SensorSettings();
    }
  }

  /// Persist settings. Returns false if the write failed, so the UI can say so
  /// instead of pretending it saved.
  Future<bool> save(SensorSettings settings) async {
    try {
      return await atClient.put(_key(), settings.encode());
    } catch (_) {
      return false;
    }
  }
}
