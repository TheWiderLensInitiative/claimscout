import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

android {
    namespace = "info.thewiderlens.claimscout"
    compileSdk = 37

    defaultConfig {
        applicationId = "info.thewiderlens.claimscout"
        minSdk = 28
        targetSdk = 37
        versionCode = 4
        versionName = "1.0.3"
        buildConfigField("String", "MS_CLIENT_ID", "\"${providers.gradleProperty("claimscout.microsoftClientId").getOrElse("")}\"")
    }

    // Release signing: the key lives outside the repo (default ~/.claimscout-release/keystore.properties, or
    // $CLAIMSCOUT_KEYSTORE_PROPS). Without it, release builds come out unsigned and debug builds still work.
    val keystoreProps = Properties().apply {
        val f = file(System.getenv("CLAIMSCOUT_KEYSTORE_PROPS") ?: "${System.getProperty("user.home")}/.claimscout-release/keystore.properties")
        if (f.exists()) f.inputStream().use { load(it) }
    }
    signingConfigs {
        if (keystoreProps.getProperty("storeFile") != null) create("release") {
            storeFile = file(keystoreProps.getProperty("storeFile"))
            storePassword = keystoreProps.getProperty("storePassword")
            keyAlias = keystoreProps.getProperty("keyAlias")
            keyPassword = keystoreProps.getProperty("keyPassword")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("release")
        }
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    packaging {
        resources.excludes += setOf("META-INF/LICENSE.md", "META-INF/NOTICE.md", "META-INF/mimetypes.default", "META-INF/mailcap.default")
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2026.09.00")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-core:1.7.8")
    implementation("androidx.core:core-ktx:1.19.1")
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.11.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.11.0")
    implementation("androidx.datastore:datastore-preferences:1.2.1")
    implementation("androidx.work:work-runtime-ktx:2.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.11.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.11.0")
    implementation("com.squareup.okhttp3:okhttp:5.5.0")
    // Gmail over IMAP with an app password: no Google Cloud project, no restricted-scope review
    implementation("com.sun.mail:android-mail:1.6.8")
    implementation("com.sun.mail:android-activation:1.6.8")
    // in-app QR scanner for pairing (many camera apps won't open claimscout:// links)
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")
    testImplementation("junit:junit:4.13.2")
}
