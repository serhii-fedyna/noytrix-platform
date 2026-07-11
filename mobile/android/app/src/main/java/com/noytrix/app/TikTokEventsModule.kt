package com.noytrix.app

import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.bridge.ReadableMap
import com.tiktok.TikTokBusinessSdk
import org.json.JSONObject

class TikTokEventsModule(reactContext: ReactApplicationContext) : ReactContextBaseJavaModule(reactContext) {
  override fun getName(): String = "TikTokEvents"

  @ReactMethod
  fun trackEvent(name: String, params: ReadableMap?) {
    try {
      if (name.isBlank()) return
      val props = params?.toHashMap()?.let { JSONObject(it as Map<*, *>) }
      TikTokBusinessSdk.trackEvent(name, props)
    } catch (_: Throwable) {
    }
  }

  @ReactMethod
  fun identify(externalId: String?, externalUserName: String?, phoneNumber: String?, email: String?) {
    try {
      val id = externalId?.takeIf { it.isNotBlank() } ?: email?.takeIf { it.isNotBlank() } ?: return
      TikTokBusinessSdk.identify(id, externalUserName, phoneNumber, email)
    } catch (_: Throwable) {
    }
  }

  @ReactMethod
  fun logout() {
    try {
      TikTokBusinessSdk.logout()
    } catch (_: Throwable) {
    }
  }
}
