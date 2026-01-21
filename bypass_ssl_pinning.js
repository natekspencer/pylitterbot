// SSL Pinning Bypass for Flutter Apps
// Targets both native Android and Flutter SSL validation

console.log("[*] Starting SSL pinning bypass...");

// Bypass Android SSL pinning
Java.perform(function() {
    console.log("[*] Hooking Android SSL verification...");
    
    // Hook SSLContext
    try {
        var SSLContext = Java.use("javax.net.ssl.SSLContext");
        SSLContext.init.overload("[Ljavax.net.ssl.KeyManager;", "[Ljavax.net.ssl.TrustManager;", "java.security.SecureRandom")
            .implementation = function(keyManager, trustManager, secureRandom) {
                console.log("[+] SSLContext.init() bypassed");
                this.init(keyManager, trustManager, secureRandom);
            };
    } catch(err) {
        console.log("[-] SSLContext hook failed: " + err);
    }

    // Hook X509TrustManager
    try {
        var X509TrustManager = Java.use("javax.net.ssl.X509TrustManager");
        var SSLContext = Java.use("javax.net.ssl.SSLContext");
        var TrustManager = Java.registerClass({
            name: "com.sensepost.test.TrustManager",
            implements: [X509TrustManager],
            methods: {
                checkClientTrusted: function(chain, authType) {},
                checkServerTrusted: function(chain, authType) {},
                getAcceptedIssuers: function() { return []; }
            }
        });
        var TrustManagers = [TrustManager.$new()];
        var SSLContext_init = SSLContext.init.overload("[Ljavax.net.ssl.KeyManager;", "[Ljavax.net.ssl.TrustManager;", "java.security.SecureRandom");
        SSLContext_init.implementation = function(keyManager, trustManager, secureRandom) {
            console.log("[+] Custom TrustManager installed");
            SSLContext_init.call(this, keyManager, TrustManagers, secureRandom);
        };
    } catch(err) {
        console.log("[-] TrustManager hook failed: " + err);
    }

    // Hook HostnameVerifier
    try {
        var HostnameVerifier = Java.use("javax.net.ssl.HostnameVerifier");
        HostnameVerifier.verify.overload("java.lang.String", "javax.net.ssl.SSLSession").implementation = function(hostname, session) {
            console.log("[+] HostnameVerifier.verify() bypassed for: " + hostname);
            return true;
        };
    } catch(err) {
        console.log("[-] HostnameVerifier hook failed: " + err);
    }

    // Hook OkHttp3 CertificatePinner (common in Flutter apps)
    try {
        var CertificatePinner = Java.use("okhttp3.CertificatePinner");
        CertificatePinner.check.overload("java.lang.String", "java.util.List").implementation = function(hostname, peerCertificates) {
            console.log("[+] okhttp3.CertificatePinner.check() bypassed for: " + hostname);
            return;
        };
    } catch(err) {
        console.log("[-] OkHttp3 CertificatePinner hook failed: " + err);
    }

    console.log("[*] Android SSL hooks complete");
});

// Flutter-specific SSL bypass
console.log("[*] Attempting Flutter SSL bypass...");
try {
    var ssl_verify_peer_cert = Module.findExportByName("libflutter.so", "ssl_verify_peer_cert");
    if (ssl_verify_peer_cert) {
        Interceptor.replace(ssl_verify_peer_cert, new NativeCallback(function() {
            console.log("[+] Flutter ssl_verify_peer_cert() bypassed");
            return 0;
        }, 'int', []));
    }
} catch(err) {
    console.log("[-] Flutter ssl_verify_peer_cert hook failed: " + err);
}

// Alternative Flutter SSL bypass via BoringSSL
try {
    var SSL_get_psk_identity = Module.findExportByName("libflutter.so", "SSL_get_psk_identity");
    if (SSL_get_psk_identity) {
        console.log("[+] Found libflutter.so, hooking SSL functions...");
        
        // Hook SSL_do_handshake
        var SSL_do_handshake = Module.findExportByName("libflutter.so", "SSL_do_handshake");
        if (SSL_do_handshake) {
            Interceptor.attach(SSL_do_handshake, {
                onEnter: function(args) {
                    console.log("[*] SSL_do_handshake called");
                },
                onLeave: function(retval) {
                    console.log("[+] SSL_do_handshake bypassed, returning 1");
                    retval.replace(1);
                }
            });
        }
    }
} catch(err) {
    console.log("[-] Flutter BoringSSL hook failed: " + err);
}

console.log("[*] SSL pinning bypass script loaded!");
