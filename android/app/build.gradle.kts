plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

android {
    namespace = "dev.trove.app"
    compileSdk = 37

    defaultConfig {
        applicationId = "dev.trove.app"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    flavorDimensions += "distribution"
    productFlavors {
        create("prod") {
            dimension = "distribution"
            buildConfigField("boolean", "ALLOW_LAN_CLEARTEXT", "false")
        }
        create("lan") {
            dimension = "distribution"
            applicationIdSuffix = ".lan"
            versionNameSuffix = "-lan"
            buildConfigField("boolean", "ALLOW_LAN_CLEARTEXT", "true")
        }
    }

    signingConfigs {
        val storePath = providers.environmentVariable("TROVE_RELEASE_STORE_FILE").orNull
            ?: providers.gradleProperty("troveReleaseStoreFile").orNull
        val storePassword = providers.environmentVariable("TROVE_RELEASE_STORE_PASSWORD").orNull
            ?: providers.gradleProperty("troveReleaseStorePassword").orNull
        val keyAlias = providers.environmentVariable("TROVE_RELEASE_KEY_ALIAS").orNull
            ?: providers.gradleProperty("troveReleaseKeyAlias").orNull
        val keyPassword = providers.environmentVariable("TROVE_RELEASE_KEY_PASSWORD").orNull
            ?: providers.gradleProperty("troveReleaseKeyPassword").orNull
        if (storePath != null && storePassword != null &&
            keyAlias != null && keyPassword != null
        ) {
            create("release") {
                storeFile = file(storePath)
                this.storePassword = storePassword
                this.keyAlias = keyAlias
                this.keyPassword = keyPassword
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            signingConfigs.findByName("release")?.let { signingConfig = it }
        }
    }

    androidComponents {
        beforeVariants(selector().all()) { variant ->
            if (variant.buildType == "release" &&
                variant.productFlavors.any { it.second == "lan" }
            ) {
                variant.enable = false
            }
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        isCoreLibraryDesugaringEnabled = true
    }

    sourceSets.getByName("test").resources.srcDir(rootProject.file("../tests/fixtures"))

    testOptions {
        unitTests.isIncludeAndroidResources = true
        unitTests.all {
            it.jvmArgs(
                "--add-opens=java.base/jdk.internal.access=ALL-UNNAMED",
                "--add-opens=java.base/java.io=ALL-UNNAMED",
            )
        }
    }
}

dependencies {
    implementation(project(":playback"))
    implementation(project(":reader"))
    implementation(project(":core"))
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.viewmodel.navigation3)
    implementation(libs.androidx.navigation3.runtime)
    implementation(libs.androidx.navigation3.ui)
    implementation(libs.androidx.work.runtime.ktx)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.material.icons.extended)
    implementation(libs.coil.compose)
    implementation(libs.coil.network.okhttp)
    coreLibraryDesugaring(libs.desugar.jdk.libs)
    debugImplementation(libs.androidx.compose.ui.tooling)
    debugImplementation(libs.androidx.compose.ui.test.manifest)

    testImplementation(libs.junit)
    testImplementation(libs.robolectric)
    testImplementation(libs.androidx.test.core)
    testImplementation(libs.androidx.test.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.turbine)
    testImplementation(libs.okhttp.mockwebserver)
    testImplementation(platform(libs.androidx.compose.bom))
    testImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.test.core)
    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.androidx.test.runner)
}
