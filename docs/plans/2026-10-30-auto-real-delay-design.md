# Design Document: Auto Real Delay Toggle

**Date:** 2026-10-30  
**Status:** Approved  
**Topic:** Configurable Automatic Speed/Latency Testing in OneXray  

---

## 1. Problem Statement & Motivation

In OneXray, automatic delay testing (pinging via HTTP/HTTPS 204 endpoints) is performed whenever subscriptions update, new outbound configs are imported, or the application launches. In addition, when connecting to an outbound proxy, `ConnectionResolver` requires nodes with measured low latency and automatically triggers active probing on unmeasured candidates (`PingDelayConstants.unknown`).

In restrictive or hostile network environments (e.g. censored networks):
1. Ping endpoints (Cloudflare/Google 204 URLs) are frequently throttled or completely blocked, causing automatic tests to fail or time out.
2. Even if proxies are functional for tunneled traffic, the pre-connection probe fails, causing `ConnectionResolutionException(ConnectionResolutionFailure.insufficientHealthyServers)` and preventing the user from connecting.
3. Subscriptions updating with dozens or hundreds of nodes trigger background probing bursts, degrading connection reliability and device performance.

Users require an explicit toggle to disable automatic delay testing across the application.

---

## 2. Proposed Architecture & Design

### 2.1 Persistence Layer
- **`PingJson` (`lib/core/model/ping_json.dart`):**
  Add `bool? autoRealDelay` field with `@JsonSerializable(explicitToJson: true, includeIfNull: false)`.
- **`PingState` (`lib/service/shared/ping/state.dart`):**
  - Add property `var autoRealDelay = true`.
  - In `readFromPreferences()`: read `pingJson.autoRealDelay` if present.
  - In `saveToPreferences()`: persist `autoRealDelay`.

### 2.2 Service & Core Execution Layer
- **`PingService` (`lib/service/shared/ping/service.dart`):**
  - Check `autoRealDelay` in:
    - `startAutomatic()`: do not schedule unmeasured nodes if `autoRealDelay` is disabled.
    - `schedulePingSubscription(int subId)` & `schedulePingSubscriptions(...)`: return immediately if `autoRealDelay` is disabled.
    - `schedulePingConfigIds(List<int> ids)`: return immediately if `autoRealDelay` is disabled.
  - Manual pings triggered directly by the user (via explicit UI action in `ServerCatalogController` / servers page) remain functional.
- **`ConnectionResolver` (`lib/service/connect/resolver.dart`):**
  - Respect `autoRealDelay` during connection candidate evaluation:
    - If `autoRealDelay` is disabled, do not launch `probeAndReread(unmeasured)`.
    - Treat candidates with `PingDelayConstants.unknown` as eligible candidates (prioritizing measured low-latency nodes when available, then falling back to unmeasured nodes) so the connection succeeds without network delay probe checks.

### 2.3 Presentation & Controller Layer
- **`XrayRuntimeController` & `XrayRuntimePageState` (`lib/pages/advanced/xray/controller.dart`):**
  - Expose `autoRealDelay` in `XrayRuntimePageState`.
  - Expose `bool get autoRealDelay => state.autoRealDelay`.
  - Expose `Future<void> toggleAutoRealDelay(bool value)` which updates local state and saves to `PingState`.
- **`XrayPage` (`lib/pages/advanced/xray/page.dart`):**
  - Add a `SettingRow` right beneath the `prototypeSpeedTest` row.
  - Contains a switch toggle bound to `controller.toggleAutoRealDelay`.
  - Displays localized title and explanatory subtitle.

### 2.4 Localization (ARB)
- Add keys in `lib/l10n/app_en.arb` and `lib/l10n/app_fa.arb`:
  - `autoRealDelayTitle`: "Auto real delay" / "تست خودکار تاخیر"
  - `autoRealDelaySubtitle`: "Automatically measure server latency on subscription update and connection." / "اندازه‌گیری خودکار تاخیر سرورها هنگام بروزرسانی اشتراک و اتصال."

---

## 3. Verification Plan
- Unit tests for `PingJson` and `PingState` persistence.
- Unit tests for `PingService` ensuring automatic queues are skipped when disabled.
- Unit tests for `ConnectionResolver` validating that unmeasured servers can be resolved without probing when `autoRealDelay` is disabled.
- Widget tests for the new `SettingRow` in `XrayPage`.
