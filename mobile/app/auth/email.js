// app/auth/email.js
import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Modal,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { useTranslation } from "react-i18next";
import Svg, { Path } from "react-native-svg";
import { useAuthStore } from "../lib/store.auth";
import { signInWithGoogle } from "../lib/googleAuth";

const UI = {
  brand: "#FFB020",
  text: "#E9EEFF",
  dim: "#BFD0FF",
  mute: "rgba(233,238,255,0.66)",
  input: "rgba(255,255,255,0.075)",
  border: "rgba(255,255,255,0.12)",
  danger: "#FF5C5C",
  good: "#29D37A",
};

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/i.test(String(value || "").trim());
}

function authCopy(lang, key) {
  const ru = {
    invalidEmail: "Проверь email: похоже, в адресе есть опечатка. Мы не сможем отправить код или привязать PRO, пока email написан неверно.",
    shortPassword: "Пароль слишком короткий. Используй минимум 6 символов, чтобы аккаунт был защищён.",
    googleConfig: "Вход через Google временно недоступен из-за настройки приложения. Email-вход работает, а Google-вход нужно проверить перед релизом.",
    googleInvalid: "Google не подтвердил вход. Попробуй ещё раз и выбери аккаунт Google, к которому хочешь привязать Noytrix.",
    googleNetwork: "Не удалось связаться с Google. Проверь интернет и попробуй снова через пару секунд.",
    googleGeneric: "Google-вход не завершился. Мы не создали аккаунт и ничего не изменили. Попробуй снова или войди по email.",
    emailDelivery: "Мы не смогли отправить код на email. Проверь адрес и попробуй снова. Если письмо не приходит, используй вход через Google.",
    loginInvalid: "Не получилось войти. Проверь email и пароль. Если не помнишь пароль, восстанови доступ ниже.",
    resetUnavailable: "Не удалось отправить код восстановления. Проверь email или попробуй вход через Google, если аккаунт был создан через Google.",
    codeInvalid: "Код не подошёл или уже устарел. Проверь последнее письмо от Noytrix и введи самый свежий код.",
  };
  const uk = {
    invalidEmail: "Перевір email: схоже, в адресі є помилка. Ми не зможемо надіслати код або прив'язати PRO, поки email написано неправильно.",
    shortPassword: "Пароль занадто короткий. Використай мінімум 6 символів, щоб акаунт був захищений.",
    googleConfig: "Вхід через Google тимчасово недоступний через налаштування застосунку. Email-вхід працює, а Google-вхід потрібно перевірити перед релізом.",
    googleInvalid: "Google не підтвердив вхід. Спробуй ще раз і вибери акаунт Google, до якого хочеш прив'язати Noytrix.",
    googleNetwork: "Не вдалося зв'язатися з Google. Перевір інтернет і спробуй ще раз за кілька секунд.",
    googleGeneric: "Google-вхід не завершився. Ми не створили акаунт і нічого не змінили. Спробуй ще раз або увійди через email.",
    emailDelivery: "Ми не змогли надіслати код на email. Перевір адресу і спробуй ще раз. Якщо лист не приходить, використай вхід через Google.",
    loginInvalid: "Не вдалося увійти. Перевір email і пароль. Якщо не пам'ятаєш пароль, віднови доступ нижче.",
    resetUnavailable: "Не вдалося надіслати код відновлення. Перевір email або спробуй вхід через Google, якщо акаунт був створений через Google.",
    codeInvalid: "Код не підійшов або вже застарів. Перевір останній лист від Noytrix і введи найсвіжіший код.",
  };
  const en = {
    invalidEmail: "Check the email address: it looks like there may be a typo. We cannot send a code or attach PRO until the email is correct.",
    shortPassword: "The password is too short. Use at least 6 characters to keep the account protected.",
    googleConfig: "Google sign-in is temporarily unavailable because of app configuration. Email sign-in still works, and Google sign-in must be checked before release.",
    googleInvalid: "Google did not confirm the sign-in. Try again and choose the Google account you want to connect to Noytrix.",
    googleNetwork: "Could not reach Google. Check your connection and try again in a few seconds.",
    googleGeneric: "Google sign-in did not finish. We did not create an account or change anything. Try again or sign in with email.",
    emailDelivery: "We could not send the email code. Check the address and try again. If the email does not arrive, use Google sign-in.",
    loginInvalid: "Could not sign in. Check your email and password. If you do not remember the password, restore access below.",
    resetUnavailable: "Could not send the recovery code. Check the email or try Google sign-in if this account was created with Google.",
    codeInvalid: "The code is invalid or expired. Check the latest email from Noytrix and enter the newest code.",
  };
  const current = String(lang || "");
  const dict = current.startsWith("uk") ? uk : current.startsWith("ru") ? ru : en;
  return dict[key] || en[key] || "";
}

function friendlyAuthError(e, lang, fallbackKey) {
  const msg = String(e?.message || "").toLowerCase();
  const detail = String(e?.data?.detail || e?.data?.message || "").toLowerCase();
  const text = `${msg} ${detail}`;

  if (text.includes("google_client_id_missing") || text.includes("redirect_uri_mismatch")) {
    return authCopy(lang, "googleConfig");
  }
  if (text.includes("google") && (text.includes("invalid") || text.includes("401") || text.includes("access_token_missing"))) {
    return authCopy(lang, "googleInvalid");
  }
  if (text.includes("network request failed") || text.includes("timeout") || text.includes("fetch")) {
    return authCopy(lang, fallbackKey === "googleGeneric" ? "googleNetwork" : fallbackKey);
  }
  if (text.includes("smtp") || text.includes("email") || text.includes("send code") || text.includes("failed to send")) {
    return authCopy(lang, "emailDelivery");
  }
  if (text.includes("invalid") && text.includes("password")) {
    return authCopy(lang, "loginInvalid");
  }
  if (text.includes("code")) {
    return authCopy(lang, "codeInvalid");
  }
  return authCopy(lang, fallbackKey);
}

export default function EmailAuth() {
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const lang = String(i18n?.language || "");

  const login = useAuthStore((s) => s.login);
  const loginGoogle = useAuthStore((s) => s.loginGoogle);
  const registerStart = useAuthStore((s) => s.registerStart);
  const registerVerify = useAuthStore((s) => s.registerVerify);
  const resetStart = useAuthStore((s) => s.resetStart);
  const resetConfirm = useAuthStore((s) => s.resetConfirm);

  const [modal, setModal] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  const [loginEmail, setLoginEmail] = useState("");
  const [loginPass, setLoginPass] = useState("");

  const [nick, setNick] = useState("");
  const [regEmail, setRegEmail] = useState("");
  const [regPass, setRegPass] = useState("");
  const [regCode, setRegCode] = useState("");
  const [regStep, setRegStep] = useState("form");

  const [resetEmail, setResetEmail] = useState("");
  const [resetCode, setResetCode] = useState("");
  const [resetPass, setResetPass] = useState("");

  const tr = (key, fb, vars = {}) => t(key, { defaultValue: fb, ...vars });

  const showNotice = (type, title, message) => {
    setNotice({
      type,
      title: String(title || "Noytrix"),
      message: String(message || ""),
    });
  };

  const close = () => {
    if (!busy) setModal(null);
  };

  const goProfile = () => {
    setModal(null);
    router.replace("/(tabs)/profile");
  };

  const onGoogle = async () => {
    setBusy(true);
    try {
      const result = await signInWithGoogle();
      if (!result?.accessToken) {
        setBusy(false);
        return;
      }
      await loginGoogle({ accessToken: result.accessToken });
      goProfile();
    } catch (e) {
      showNotice(
        "error",
        tr("auth.errorTitle", "Error"),
        friendlyAuthError(e, lang, "googleGeneric")
      );
    } finally {
      setBusy(false);
    }
  };

  const onLogin = async () => {
    const email = loginEmail.trim().toLowerCase();

    if (!email || !loginPass) {
      return showNotice(
        "error",
        tr("auth.errorTitle", "Error"),
        tr("auth.alertLoginEmpty", "Enter email and password.")
      );
    }

    if (!isValidEmail(email)) {
      return showNotice("error", tr("auth.errorTitle", "Error"), authCopy(lang, "invalidEmail"));
    }

    setBusy(true);
    try {
      await login({ email, password: loginPass });
      goProfile();
    } catch (e) {
      showNotice(
        "error",
        tr("auth.errorTitle", "Error"),
        friendlyAuthError(e, lang, "loginInvalid")
      );
    } finally {
      setBusy(false);
    }
  };

  const onRegisterStart = async () => {
    const email = regEmail.trim().toLowerCase();

    if (!nick.trim() || !email || !regPass) {
      return showNotice(
        "error",
        tr("auth.errorTitle", "Error"),
        tr("auth.alertRegisterEmpty", "Fill in nickname, email and password.")
      );
    }

    if (!isValidEmail(email)) {
      return showNotice("error", tr("auth.errorTitle", "Error"), authCopy(lang, "invalidEmail"));
    }

    if (String(regPass || "").length < 6) {
      return showNotice("error", tr("auth.errorTitle", "Error"), authCopy(lang, "shortPassword"));
    }

    setBusy(true);
    try {
      await registerStart({
        email,
        password: regPass,
        nick: nick.trim(),
      });

      setRegStep("code");
      showNotice(
        "success",
        tr("auth.alertRegisterCodeSentTitle", "Code sent"),
        tr("auth.alertRegisterCodeSentText", "We sent a verification code to your email.")
      );
    } catch (e) {
      showNotice(
        "error",
        tr("auth.errorTitle", "Error"),
        friendlyAuthError(e, lang, "emailDelivery")
      );
    } finally {
      setBusy(false);
    }
  };

  const onRegisterVerify = async () => {
    const email = regEmail.trim().toLowerCase();

    if (!regCode.trim()) {
      return showNotice(
        "error",
        tr("auth.errorTitle", "Error"),
        tr("auth.alertRegisterInvalidCode", "Invalid or expired code.")
      );
    }

    setBusy(true);
    try {
      await registerVerify({
        email,
        code: regCode.trim(),
        nick: nick.trim(),
        password: regPass,
      });

      showNotice(
        "success",
        tr("auth.successTitle", "Success"),
        tr("auth.alertRegisterSuccess", "Account confirmed. You are now signed in.")
      );

      setTimeout(goProfile, 350);
    } catch (e) {
      showNotice(
        "error",
        tr("auth.errorTitle", "Error"),
        friendlyAuthError(e, lang, "codeInvalid")
      );
    } finally {
      setBusy(false);
    }
  };

  const onResetStart = async () => {
    const email = resetEmail.trim().toLowerCase();

    if (!email) {
      return showNotice(
        "error",
        tr("auth.errorTitle", "Error"),
        tr("auth.alertResetEnterEmail", "Enter email to receive a code.")
      );
    }

    if (!isValidEmail(email)) {
      return showNotice("error", tr("auth.errorTitle", "Error"), authCopy(lang, "invalidEmail"));
    }

    setBusy(true);
    try {
      await resetStart({ email });
      showNotice(
        "success",
        tr("auth.successTitle", "Success"),
        tr("auth.alertResetCodeSent", "Check your email.")
      );
    } catch (e) {
      showNotice(
        "error",
        tr("auth.errorTitle", "Error"),
        friendlyAuthError(e, lang, "resetUnavailable")
      );
    } finally {
      setBusy(false);
    }
  };

  const onResetConfirm = async () => {
    const email = resetEmail.trim().toLowerCase();

    if (!email || !resetCode.trim() || !resetPass) {
      return showNotice(
        "error",
        tr("auth.errorTitle", "Error"),
        tr("auth.alertResetError", "Failed to reset password.")
      );
    }

    if (!isValidEmail(email)) {
      return showNotice("error", tr("auth.errorTitle", "Error"), authCopy(lang, "invalidEmail"));
    }

    if (String(resetPass || "").length < 6) {
      return showNotice("error", tr("auth.errorTitle", "Error"), authCopy(lang, "shortPassword"));
    }

    setBusy(true);
    try {
      await resetConfirm({
        email,
        code: resetCode.trim(),
        new_password: resetPass,
      });

      setModal(null);
      showNotice(
        "success",
        tr("auth.successTitle", "Success"),
        tr("auth.alertResetSuccess", "Password changed. Log in with your new password.")
      );
    } catch (e) {
      showNotice(
        "error",
        tr("auth.errorTitle", "Error"),
        friendlyAuthError(e, lang, "resetUnavailable")
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.wrap}>
      <LinearGradient
        colors={["rgba(10,18,51,0.96)", "rgba(7,16,43,0.98)", "rgba(8,14,36,0.98)"]}
        style={styles.innerCard}
      >
        <Text style={styles.title}>{tr("auth.title", "Sign in / Sign up")}</Text>
        <Text style={styles.subtitle}>{tr("auth.subtitle", "Choose a method.")}</Text>

        <TouchableOpacity
          disabled={busy}
          activeOpacity={0.88}
          onPress={onGoogle}
          style={[styles.googleBtn, busy && styles.disabled]}
        >
          <View style={styles.googleIcon}>
            <GoogleG />
          </View>
          <Text numberOfLines={1} adjustsFontSizeToFit style={styles.googleText}>
            {tr("auth.googleBtn", "Continue with Google")}
          </Text>
        </TouchableOpacity>

        <MainButton
          orange
          icon="log-in-outline"
          title={tr("auth.loginEmailBtn", "Sign in with email")}
          onPress={() => setModal("login")}
        />

        <MainButton
          icon="person-add-outline"
          title={tr("auth.registerBtn", "Create account")}
          onPress={() => {
            setRegStep("form");
            setModal("register");
          }}
        />

        <TouchableOpacity activeOpacity={0.75} onPress={() => setModal("reset")}>
          <Text style={styles.forgot}>{tr("auth.forgotPassword", "Forgot password?")}</Text>
        </TouchableOpacity>
      </LinearGradient>

      <AuthModal visible={modal === "login"} onClose={close}>
        <Text style={styles.modalTitle}>{tr("auth.loginTitle", "Sign in with email")}</Text>

        <Input
          value={loginEmail}
          onChangeText={setLoginEmail}
          placeholder={tr("auth.emailPlaceholder", "Email")}
          keyboardType="email-address"
        />

        <Input
          value={loginPass}
          onChangeText={setLoginPass}
          placeholder={tr("auth.passwordPlaceholder", "Password")}
          secureTextEntry
        />

        <ActionButton
          busy={busy}
          icon="log-in-outline"
          title={busy ? tr("auth.confirmCodeLoadingBtn", "Checking...") : tr("auth.loginBtn", "Sign in")}
          onPress={onLogin}
        />

        <Cancel title={tr("auth.cancelBtn", "Cancel")} onPress={close} />
      </AuthModal>

      <AuthModal visible={modal === "register"} onClose={close}>
        <Text style={styles.modalTitle}>
          {regStep === "form"
            ? tr("auth.registerTitle", "Create account")
            : tr("auth.registerVerifyTitle", "Confirm registration")}
        </Text>

        {regStep === "code" && (
          <Text style={styles.verifyText}>
            {tr(
              "auth.registerVerifyText",
              "We sent a verification code to {{email}}. Enter it to complete registration.",
              { email: regEmail.trim().toLowerCase() }
            )}
          </Text>
        )}

        {regStep === "form" ? (
          <>
            <Input
              value={nick}
              onChangeText={setNick}
              placeholder={tr("auth.nicknamePlaceholder", "Nickname")}
            />

            <Input
              value={regEmail}
              onChangeText={setRegEmail}
              placeholder={tr("auth.emailPlaceholder", "Email")}
              keyboardType="email-address"
            />

            <Input
              value={regPass}
              onChangeText={setRegPass}
              placeholder={tr("auth.passwordPlaceholder", "Password")}
              secureTextEntry
            />

            <ActionButton
              busy={busy}
              icon="mail-outline"
              title={busy ? tr("auth.getCodeLoadingBtn", "Sending...") : tr("auth.getCodeBtn", "Get code")}
              onPress={onRegisterStart}
            />
          </>
        ) : (
          <>
            <Input
              value={regCode}
              onChangeText={setRegCode}
              placeholder={tr("auth.codePlaceholder", "Code from email")}
              keyboardType="number-pad"
            />

            <ActionButton
              busy={busy}
              icon="checkmark-circle-outline"
              title={busy ? tr("auth.confirmCodeLoadingBtn", "Checking...") : tr("auth.confirmCodeBtn", "Confirm code")}
              onPress={onRegisterVerify}
            />

            <TouchableOpacity
              activeOpacity={0.75}
              disabled={busy}
              onPress={onRegisterStart}
              style={styles.resendBtn}
            >
              <Text style={styles.resendText}>{tr("auth.resendCodeBtn", "Resend code")}</Text>
            </TouchableOpacity>
          </>
        )}

        <Cancel title={tr("auth.cancelBtn", "Cancel")} onPress={close} />
      </AuthModal>

      <AuthModal visible={modal === "reset"} onClose={close}>
        <Text style={styles.modalTitle}>{tr("auth.resetTitle", "Change password")}</Text>

        <Input
          value={resetEmail}
          onChangeText={setResetEmail}
          placeholder={tr("auth.emailPlaceholder", "Email")}
          keyboardType="email-address"
        />

        <ActionButton
          dark
          busy={busy}
          icon="mail-open-outline"
          title={busy ? tr("auth.getCodeLoadingBtn", "Sending...") : tr("auth.getCodeBtn", "Get code")}
          onPress={onResetStart}
        />

        <Input
          value={resetCode}
          onChangeText={setResetCode}
          placeholder={tr("auth.codePlaceholder", "Code from email")}
          keyboardType="number-pad"
        />

        <Input
          value={resetPass}
          onChangeText={setResetPass}
          placeholder={tr("auth.newPasswordPlaceholder", "New password")}
          secureTextEntry
        />

        <ActionButton
          busy={busy}
          icon="save-outline"
          title={busy ? tr("auth.changePasswordLoadingBtn", "Checking...") : tr("auth.changePasswordBtn", "Change password")}
          onPress={onResetConfirm}
        />

        <Cancel title={tr("auth.cancelBtn", "Cancel")} onPress={close} />
      </AuthModal>

      <PremiumNotice
        notice={notice}
        onClose={() => setNotice(null)}
        okText={tr("auth.okBtn", "OK")}
      />
    </View>
  );
}

function PremiumNotice({ notice, onClose, okText }) {
  if (!notice) return null;

  const isSuccess = notice.type === "success";
  const color = isSuccess ? UI.good : UI.danger;
  const icon = isSuccess ? "checkmark-circle-outline" : "alert-circle-outline";

  return (
    <Modal transparent visible animationType="fade" statusBarTranslucent onRequestClose={onClose}>
      <View style={styles.noticeOverlay}>
        <View style={styles.noticeCard}>
          <View style={[styles.noticeIcon, { borderColor: color, backgroundColor: `${color}22` }]}>
            <Ionicons name={icon} size={30} color={color} />
          </View>

          <Text style={styles.noticeTitle}>{notice.title}</Text>
          {!!notice.message && <Text style={styles.noticeMessage}>{notice.message}</Text>}

          <TouchableOpacity activeOpacity={0.88} style={styles.noticeButton} onPress={onClose}>
            <Text style={styles.noticeButtonText}>{okText}</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

function MainButton({ orange, icon, title, onPress }) {
  return (
    <TouchableOpacity
      activeOpacity={0.88}
      onPress={onPress}
      style={[styles.mainBtn, orange ? styles.mainOrange : styles.mainDark]}
    >
      <Ionicons name={icon} size={22} color={orange ? "#07101f" : UI.text} />
      <Text numberOfLines={1} adjustsFontSizeToFit style={[styles.mainBtnText, { color: orange ? "#07101f" : UI.text }]}>
        {title}
      </Text>
    </TouchableOpacity>
  );
}

function AuthModal({ visible, children, onClose }) {
  return (
    <Modal visible={visible} transparent animationType="fade" statusBarTranslucent onRequestClose={onClose}>
      <KeyboardAvoidingView style={styles.overlay} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <TouchableOpacity style={styles.backdrop} activeOpacity={1} onPress={onClose} />

        <ScrollView contentContainerStyle={styles.modalScroll} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          <LinearGradient colors={["#111B33", "#0D1427", "#091126"]} style={styles.modalCard}>
            {children}
          </LinearGradient>
        </ScrollView>
      </KeyboardAvoidingView>
    </Modal>
  );
}

function Input(props) {
  return (
    <TextInput
      {...props}
      style={styles.input}
      placeholderTextColor="rgba(233,238,255,0.48)"
      autoCapitalize="none"
      autoCorrect={false}
    />
  );
}

function ActionButton({ busy, icon, title, onPress, dark }) {
  return (
    <TouchableOpacity
      disabled={busy}
      activeOpacity={0.88}
      onPress={onPress}
      style={[styles.actionBtn, dark && styles.actionDark, busy && styles.disabled]}
    >
      {busy ? (
        <ActivityIndicator color={dark ? UI.text : "#07101f"} />
      ) : (
        <>
          <Ionicons name={icon} size={22} color={dark ? UI.text : "#07101f"} />
          <Text numberOfLines={1} adjustsFontSizeToFit style={[styles.actionText, { color: dark ? UI.text : "#07101f" }]}>
            {title}
          </Text>
        </>
      )}
    </TouchableOpacity>
  );
}

function Cancel({ title, onPress }) {
  return (
    <TouchableOpacity activeOpacity={0.75} style={styles.cancelBtn} onPress={onPress}>
      <Text style={styles.cancelText}>{title}</Text>
    </TouchableOpacity>
  );
}

function GoogleG() {
  return (
    <Svg width={20} height={20} viewBox="0 0 48 48">
      <Path fill="#FFC107" d="M43.61 20.08H42V20H24v8h11.3C33.65 32.66 29.22 36 24 36c-6.63 0-12-5.37-12-12s5.37-12 12-12c3.06 0 5.84 1.15 7.96 3.04l5.66-5.66C34.05 6.05 29.26 4 24 4 12.95 4 4 12.95 4 24s8.95 20 20 20 20-8.95 20-20c0-1.34-.14-2.65-.39-3.92z" />
      <Path fill="#FF3D00" d="M6.31 14.69l6.57 4.82C14.66 15.1 18.98 12 24 12c3.06 0 5.84 1.15 7.96 3.04l5.66-5.66C34.05 6.05 29.26 4 24 4 16.32 4 9.66 8.34 6.31 14.69z" />
      <Path fill="#4CAF50" d="M24 44c5.17 0 9.86-1.98 13.41-5.19l-6.19-5.24C29.21 35.09 26.72 36 24 36c-5.2 0-9.62-3.31-11.28-7.93l-6.52 5.02C9.5 39.56 16.23 44 24 44z" />
      <Path fill="#1976D2" d="M43.61 20.08H42V20H24v8h11.3c-.79 2.24-2.23 4.17-4.08 5.57l6.19 5.24C36.97 39.21 44 34 44 24c0-1.34-.14-2.65-.39-3.92z" />
    </Svg>
  );
}

const styles = StyleSheet.create({
  wrap: { width: "100%" },

  innerCard: {
    borderRadius: 24,
    padding: 22,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
    overflow: "hidden",
  },

  title: {
    color: UI.brand,
    fontSize: 25,
    lineHeight: 31,
    fontWeight: "900",
  },

  subtitle: {
    marginTop: 8,
    color: UI.mute,
    fontSize: 15,
    lineHeight: 21,
    fontWeight: "700",
  },

  verifyText: {
    marginTop: -6,
    marginBottom: 14,
    color: UI.mute,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: "700",
  },

  mainBtn: {
    height: 56,
    borderRadius: 16,
    marginTop: 14,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
  },

  mainOrange: {
    marginTop: 18,
    backgroundColor: UI.brand,
  },

  mainDark: {
    backgroundColor: "rgba(255,255,255,0.075)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.10)",
  },

  mainBtnText: {
    fontSize: 16,
    fontWeight: "900",
  },

  forgot: {
    marginTop: 18,
    textAlign: "center",
    color: UI.mute,
    fontSize: 14,
    fontWeight: "800",
    textDecorationLine: "underline",
  },

  googleBtn: {
    height: 58,
    borderRadius: 18,
    marginTop: 18,
    paddingHorizontal: 14,
    backgroundColor: "#F4F7FB",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.20)",
  },

  googleIcon: {
    width: 30,
    height: 30,
    borderRadius: 999,
    backgroundColor: "#ffffff",
    alignItems: "center",
    justifyContent: "center",
  },

  googleText: {
    color: "#1F2937",
    fontSize: 16,
    fontWeight: "900",
  },

  overlay: { flex: 1, justifyContent: "center" },

  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.68)",
  },

  modalScroll: {
    flexGrow: 1,
    justifyContent: "center",
    paddingHorizontal: 18,
    paddingVertical: 44,
  },

  modalCard: {
    width: "100%",
    borderRadius: 24,
    padding: 20,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.14)",
    overflow: "hidden",
  },

  modalTitle: {
    color: UI.text,
    fontSize: 24,
    lineHeight: 30,
    fontWeight: "900",
    marginBottom: 16,
  },

  input: {
    height: 56,
    borderRadius: 16,
    marginBottom: 12,
    paddingHorizontal: 16,
    color: UI.text,
    fontSize: 16,
    fontWeight: "700",
    backgroundColor: UI.input,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.10)",
  },

  actionBtn: {
    height: 56,
    borderRadius: 16,
    marginTop: 4,
    backgroundColor: UI.brand,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
  },

  actionDark: {
    marginBottom: 12,
    backgroundColor: "rgba(255,255,255,0.075)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.10)",
  },

  actionText: {
    fontSize: 16,
    fontWeight: "900",
  },

  resendBtn: {
    marginTop: 14,
    alignItems: "center",
  },

  resendText: {
    color: UI.brand,
    fontSize: 14,
    fontWeight: "900",
    textDecorationLine: "underline",
  },

  cancelBtn: {
    marginTop: 18,
    alignItems: "center",
  },

  cancelText: {
    color: UI.mute,
    fontSize: 15,
    fontWeight: "800",
    textDecorationLine: "underline",
  },

  noticeOverlay: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.72)",
    justifyContent: "center",
    paddingHorizontal: 24,
  },

  noticeCard: {
    borderRadius: 26,
    padding: 22,
    alignItems: "center",
    backgroundColor: "#0D1427",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.14)",
  },

  noticeIcon: {
    width: 62,
    height: 62,
    borderRadius: 999,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 14,
  },

  noticeTitle: {
    color: UI.text,
    fontSize: 22,
    fontWeight: "900",
    textAlign: "center",
  },

  noticeMessage: {
    marginTop: 8,
    color: UI.mute,
    fontSize: 15,
    lineHeight: 21,
    fontWeight: "700",
    textAlign: "center",
  },

  noticeButton: {
    marginTop: 20,
    height: 52,
    borderRadius: 16,
    backgroundColor: UI.brand,
    alignItems: "center",
    justifyContent: "center",
    alignSelf: "stretch",
  },

  noticeButtonText: {
    color: "#07101f",
    fontSize: 16,
    fontWeight: "900",
  },

  disabled: { opacity: 0.6 },
});
