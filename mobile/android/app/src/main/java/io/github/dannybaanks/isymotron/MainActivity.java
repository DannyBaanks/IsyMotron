package io.github.dannybaanks.isymotron;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override public void onCreate(Bundle savedInstanceState) {
        registerPlugin(GusLocalPlugin.class);
        registerPlugin(GusSecretsPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
