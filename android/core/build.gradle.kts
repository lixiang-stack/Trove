plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ksp)
}

android {
    namespace = "dev.trove.core"
    compileSdk = 37

    defaultConfig {
        minSdk = 26
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.isIncludeAndroidResources = true
        unitTests.all {
            it.jvmArgs(
                "--add-opens=java.base/jdk.internal.access=ALL-UNNAMED",
                "--add-opens=java.base/java.io=ALL-UNNAMED",
            )
        }
    }

    sourceSets.getByName("test").resources.srcDir(rootProject.file("../contract"))
    sourceSets.getByName("test").resources.srcDir(rootProject.file("../tests/fixtures"))
    sourceSets.getByName("test").assets.srcDir("$projectDir/schemas")
}

ksp {
    arg("room.schemaLocation", "$projectDir/schemas")
}

dependencies {
    implementation(libs.kotlinx.coroutines.core)
    api(libs.kotlinx.serialization.json)
    api(libs.retrofit)
    implementation(libs.retrofit.kotlinx.serialization)
    implementation(libs.okhttp)
    api(libs.androidx.room.runtime)
    api(libs.androidx.room.ktx)
    implementation(libs.androidx.sqlite.bundled)
    implementation(libs.androidx.datastore.preferences)
    implementation(libs.androidx.work.runtime.ktx)
    ksp(libs.androidx.room.compiler)

    testImplementation(libs.junit)
    testImplementation(libs.robolectric)
    testImplementation(libs.turbine)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.okhttp.mockwebserver)
    testImplementation(libs.androidx.test.core)
    testImplementation(libs.androidx.sqlite.framework)
    testImplementation(libs.androidx.room.testing)

    androidTestImplementation(libs.androidx.test.core)
    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.androidx.test.runner)
}
