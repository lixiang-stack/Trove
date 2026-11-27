import org.gradle.api.tasks.testing.Test

plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.android.library) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.ksp) apply false
}

// Robolectric otherwise downloads android-all jars at test runtime. Fetch them
// through Gradle and point every test JVM at the local repository instead.
// One configuration per SDK: a shared configuration would resolve both versions
// to the highest one and leave the other missing for the test JVM.
val robolectricArtifacts = listOf(
    // SDK 36 for @Config(sdk = [36]) tests; SDK 37 for tests using the default.
    // Keep these in sync when upgrading Robolectric.
    "org.robolectric:android-all-instrumented:16-robolectric-13921718-i7",
    "org.robolectric:android-all-instrumented:17-robolectric-15733970-i7",
)
val robolectricRuntimes = robolectricArtifacts.mapIndexed { index, notation ->
    configurations.create("robolectricRuntime$index") {
        isCanBeConsumed = false
        isCanBeResolved = true
    }.also { configuration ->
        dependencies.add(configuration.name, notation)
    }
}

val robolectricRepoDir = layout.buildDirectory.dir("robolectric-repo")

val prepareRobolectricDeps = tasks.register("prepareRobolectricDeps") {
    inputs.files(robolectricRuntimes)
    outputs.dir(robolectricRepoDir)
    doLast {
        val repository = robolectricRepoDir.get().asFile
        robolectricRuntimes.forEach { configuration ->
            configuration.resolvedConfiguration.resolvedArtifacts.forEach { artifact ->
                val id = artifact.moduleVersion.id
                val target = repository.resolve(
                    "${id.group.replace('.', '/')}/${id.name}/${id.version}/${artifact.file.name}"
                )
                target.parentFile.mkdirs()
                artifact.file.copyTo(target, overwrite = true)
            }
        }
    }
}

subprojects {
    tasks.withType<Test>().configureEach {
        dependsOn(prepareRobolectricDeps)
        systemProperty("maven.repo.local", robolectricRepoDir.get().asFile.absolutePath)
    }
}
