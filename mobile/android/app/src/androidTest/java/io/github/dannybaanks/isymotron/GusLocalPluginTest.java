package io.github.dannybaanks.isymotron;

import static org.junit.Assert.assertNotNull;

import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class GusLocalPluginTest {
    @Test public void localAndSecretPluginsAreRegisteredBeforeTheBridgeStarts() {
        try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
            scenario.onActivity(activity -> {
                assertNotNull(activity.getBridge().getPlugin("GusLocal"));
                assertNotNull(activity.getBridge().getPlugin("GusSecrets"));
            });
        }
    }
}
