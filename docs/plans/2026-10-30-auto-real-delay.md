# Auto Real Delay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Provide an optional "Auto real delay" setting in Xray advanced settings to disable automatic latency probing during subscription updates, application startup, and server connection resolution.

**Architecture:** Extend `PingJson` and `PingState` to persist the `autoRealDelay` preference (defaulting to `true`). In `PingService`, gate all automatic background and subscription-triggered ping scheduling behind this flag. In `ConnectionResolver`, allow connection candidates with unmeasured (`unknown`) delay without triggering blocking network probes when `autoRealDelay` is `false`. Surface a toggle `SettingRow` in `XrayPage` wired to `XrayRuntimeController`, backed by ARB localizations.

**Tech Stack:** Dart, Flutter, Bloc/Cubit (`PageCubit`), Drift, `json_serializable`, Flutter ARB localization (`flutter gen-l10n`).

---

### Task 1: Model & Persistence Extension (`PingJson` & `PingState`)

**Files:**
- Modify: `lib/core/model/ping_json.dart:5-17`
- Modify: `lib/core/model/ping_json.g.dart` (regenerated via `dart run build_runner build`)
- Modify: `lib/service/shared/ping/state.dart:38-78`
- Test: `test/service/shared/ping/state_test.dart`

**Step 1: Write the failing unit test for `PingState` autoRealDelay persistence**
Create or update `test/service/shared/ping/state_test.dart`:
```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:onexray/service/shared/ping/state.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
  });

  test('PingState defaults autoRealDelay to true and persists mutations', () async {
    final state = PingState();
    expect(state.autoRealDelay, isTrue);

    state.autoRealDelay = false;
    await state.saveToPreferences();

    final reloaded = PingState();
    await reloaded.readFromPreferences();
    expect(reloaded.autoRealDelay, isFalse);
  });
}
```

**Step 2: Run test to verify it fails**
Run: `flutter test test/service/shared/ping/state_test.dart`
Expected: Compilation failure or missing getter `autoRealDelay`.

**Step 3: Update `PingJson` and `PingState` implementation**
In `lib/core/model/ping_json.dart`:
```dart
@JsonSerializable(explicitToJson: true, includeIfNull: false)
class PingJson {
  double? timeout;
  String? url;
  String? customUrl;
  bool? autoRealDelay;

  PingJson(this.timeout, this.url, this.customUrl, [this.autoRealDelay]);
...
```
In `lib/service/shared/ping/state.dart`:
```dart
class PingState {
  var timeout = PingTimeout.defaultValue;
  var url = PingUrl.cloudflare;
  var customUrl = "";
  var autoRealDelay = true;
...
  Future<void> readFromPreferences() async {
    ...
    if (pingJson.autoRealDelay != null) {
      autoRealDelay = pingJson.autoRealDelay!;
    }
  }

  Future<void> saveToPreferences() async {
    final pingJson = PingJson(timeout, url.name, customUrl, autoRealDelay);
    await PreferencesKey().savePingState(pingJson.toJson());
  }
```

**Step 4: Run test to verify it passes**
Run: `flutter test test/service/shared/ping/state_test.dart`
Expected: PASS

---

### Task 2: Service-Layer Automatic Ping Gating (`PingService`)

**Files:**
- Modify: `lib/service/shared/ping/service.dart:50-137`
- Test: `test/service/shared/ping/service_test.dart`

**Step 1: Write failing unit test for `PingService` respecting `autoRealDelay`**
In `test/service/shared/ping/service_test.dart`, add a test verifying that when `autoRealDelay` is false, `schedulePingSubscription` and `startAutomatic` do not enqueue probe jobs.

**Step 2: Run test to verify it fails**
Run: `flutter test test/service/shared/ping/service_test.dart`
Expected: FAIL

**Step 3: Implement gating in `PingService`**
In `lib/service/shared/ping/service.dart`:
```dart
  void startAutomatic() {
    if (_automaticEnabled) return;
    _automaticEnabled = true;
    unawaited(
      _scheduleUnmeasured().catchError((Object error, StackTrace stackTrace) {
        ygLogger(
          'Schedule unmeasured nodes failed (${error.runtimeType})\n$stackTrace',
        );
      }),
    );
  }

  Future<void> _scheduleUnmeasured() async {
    final pingState = PingState();
    await pingState.readFromPreferences();
    if (!pingState.autoRealDelay) return;
    final ids = await _database.coreConfigDao.unmeasuredOutboundIds;
    schedulePingConfigIds(ids);
  }

  void schedulePingConfigIds(List<int> ids) {
    if (!_automaticEnabled || _pingQueue.isPaused) return;
    unawaited(() async {
      final pingState = PingState();
      await pingState.readFromPreferences();
      if (!pingState.autoRealDelay) return;
      await pingConfigIds(ids);
    }());
  }

  void schedulePingSubscriptions(Iterable<int> subIds) {
    if (!_automaticEnabled || _pingQueue.isPaused) return;
    final targetSubIds = subIds
        .where((id) => id > DBConstants.defaultId)
        .toSet()
        .toList(growable: false);
    for (final subId in targetSubIds) {
      unawaited(
        _enqueuePing(() async {
          final pingState = PingState();
          await pingState.readFromPreferences();
          if (!pingState.autoRealDelay) return;
          final db = _database;
          final rows = (await db.coreConfigDao.allOutboundRowsWithDataBySubId(
            subId,
          )).where(isUnmeasured).toList();
          if (rows.isNotEmpty) await _pingConfigs(db, rows);
        }),
      );
    }
  }
```

**Step 4: Run test to verify it passes**
Run: `flutter test test/service/shared/ping/service_test.dart`
Expected: PASS

---

### Task 3: Connection Candidate Resolution Without Probe (`ConnectionResolver`)

**Files:**
- Modify: `lib/service/connect/resolver.dart:213-254`
- Test: `test/service/connect/resolver_test.dart`

**Step 1: Write failing unit test for `ConnectionResolver` with `autoRealDelay == false`**
In `test/service/connect/resolver_test.dart`, test that when candidate nodes only have `PingDelayConstants.unknown`, and `autoRealDelay` is disabled, resolution succeeds with the unmeasured candidate rather than throwing `insufficientHealthyServers` or triggering `_probe`.

**Step 2: Run test to verify it fails**
Run: `flutter test test/service/connect/resolver_test.dart`
Expected: FAIL

**Step 3: Update `ConnectionResolver`**
In `lib/service/connect/resolver.dart`:
Read `pingState.autoRealDelay`. When `successful.length < required`:
If `!pingState.autoRealDelay`:
Include unmeasured candidates (`candidate.row.delay == PingDelayConstants.unknown`) into eligible resolved entries without triggering `probeAndReread`.

**Step 4: Run test to verify it passes**
Run: `flutter test test/service/connect/resolver_test.dart`
Expected: PASS

---

### Task 4: Controller & State Integration (`XrayRuntimeController`)

**Files:**
- Modify: `lib/pages/advanced/xray/controller.dart:23-91, 160-220`
- Test: `test/pages/advanced/xray/controller_test.dart`

**Step 1: Write failing unit test for `XrayRuntimeController.toggleAutoRealDelay`**
Verify that calling `toggleAutoRealDelay(false)` updates `state.autoRealDelay` and persists to `PingState`.

**Step 2: Run test to verify it fails**
Run: `flutter test test/pages/advanced/xray/controller_test.dart`
Expected: FAIL

**Step 3: Implement `autoRealDelay` in controller & state**
Add `autoRealDelay` to `XrayRuntimePageState` (default `true`).
In `XrayRuntimeController.load()`:
Read `preferences.autoRealDelay` and emit in state.
Add method:
```dart
  Future<void> toggleAutoRealDelay(bool value) async {
    emit(state.copyWith(autoRealDelay: value));
    final pingState = PingState();
    await pingState.readFromPreferences();
    pingState.autoRealDelay = value;
    await pingState.saveToPreferences();
  }
```

**Step 4: Run test to verify it passes**
Run: `flutter test test/pages/advanced/xray/controller_test.dart`
Expected: PASS

---

### Task 5: Localization & UI Presentation (`XrayPage`)

**Files:**
- Modify: `lib/l10n/app_en.arb`
- Modify: `lib/l10n/app_fa.arb`
- Modify: `lib/l10n/app_ru.arb`
- Modify: `lib/l10n/app_zh.arb`
- Modify: `lib/l10n/app_zh_Hant.arb`
- Run: `flutter gen-l10n`
- Modify: `lib/pages/advanced/xray/page.dart:165-180`
- Test: `test/pages/advanced/xray/page_test.dart`

**Step 1: Add localization entries**
In `lib/l10n/app_en.arb`:
```json
  "autoRealDelayTitle": "Auto real delay",
  "@autoRealDelayTitle": {
    "description": "Title for automatic delay testing toggle in Xray advanced settings"
  },
  "autoRealDelaySubtitle": "Automatically measure server latency on subscription update and connection.",
  "@autoRealDelaySubtitle": {
    "description": "Subtitle describing auto real delay behavior"
  }
```
In `lib/l10n/app_fa.arb`:
```json
  "autoRealDelayTitle": "تست خودکار تاخیر",
  "autoRealDelaySubtitle": "اندازه‌گیری خودکار تاخیر سرورها هنگام بروزرسانی اشتراک و برقراری اتصال."
```
Run `flutter gen-l10n`.

**Step 2: Add `SettingRow` in `lib/pages/advanced/xray/page.dart`**
Directly under `_pushRow` for `l.prototypeSpeedTest`:
```dart
SettingRow(
  title: l.autoRealDelayTitle,
  subtitle: l.autoRealDelaySubtitle,
  titleStyle: mobile ? AppTypography.settingsSelect : null,
  trailing: Switch(
    value: state.autoRealDelay,
    onChanged: state.saving || controller.busy
        ? null
        : (value) => controller.toggleAutoRealDelay(value),
  ),
),
```

**Step 3: Run widget test to verify UI renders and toggles**
Run: `flutter test test/pages/advanced/xray/page_test.dart`
Expected: PASS

---

### Task 6: Full Verification & Static Analysis

**Commands:**
- `flutter test`
- `git diff --check`
