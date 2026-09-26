
"""Windows port of build.sh: javac -> d8 -> aapt2 -> zip -> zipalign -> sign."""
import pathlib, subprocess, shutil, sys, zipfile, os

PROJ = pathlib.Path(r"C:\Users\26503\Desktop\DeepSeek\github项目\WeChat-LiquidGlass")
TOOL = PROJ / "tools"
OUT  = PROJ / "build"
BT   = TOOL / "bt" / "android-14"
PLAT = TOOL / "plat" / "android-34" / "android.jar"
XAPI = TOOL / "xapi" / "classes.jar"
JAVA = shutil.which("java"); JAVAC = shutil.which("javac")

import re
mf = (PROJ / "AndroidManifest.xml").read_text(encoding="utf-8")
VERSION = re.search(r'android:versionName="([^"]*)"', mf).group(1)
print("version:", VERSION)

def run(cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd[:4]), "..." if len(cmd) > 4 else "")
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if p.returncode != 0:
        print("FAILED rc=", p.returncode)
        print("STDOUT:", p.stdout[-4000:])
        print("STDERR:", p.stderr[-4000:])
        sys.exit(1)
    if p.stdout.strip(): print("   ", p.stdout.strip()[:2000])
    if p.stderr.strip(): print("  [e]", p.stderr.strip()[:2000])
    return p

if OUT.exists(): shutil.rmtree(OUT)
(OUT / "classes").mkdir(parents=True); (OUT / "dex").mkdir(parents=True)

print("[1/7] javac")
srcs = sorted(str(p) for p in (PROJ / "src").rglob("*.java"))
(OUT / "sources.txt").write_text("\n".join(srcs), encoding="utf-8")
run([JAVAC, "-encoding", "UTF-8", "--release", "11", "-Xlint:-options",
     "-classpath", f"{PLAT};{XAPI}", "-d", str(OUT / "classes")] + srcs)

print("[2/7] jar + d8")
run([shutil.which("jar"), "cf", str(OUT / "classes.jar"), "-C", str(OUT / "classes"), "."])
run([JAVA, "-cp", str(BT / "lib" / "d8.jar"), "com.android.tools.r8.D8",
     "--release", "--lib", str(PLAT), "--min-api", "26",
     "--output", str(OUT / "dex"), str(OUT / "classes.jar")])

print("[3/7] aapt2 compile/link")
run([str(BT / "aapt2.exe"), "compile", "--dir", str(PROJ / "res"), "-o", str(OUT / "res.zip")])
run([str(BT / "aapt2.exe"), "link", "-o", str(OUT / "base.apk"), "-I", str(PLAT),
     "--manifest", str(PROJ / "AndroidManifest.xml"), str(OUT / "res.zip")])

print("[4/7] inject classes.dex + META-INF/xposed")
shutil.copy(OUT / "base.apk", OUT / "unsigned.apk")
STAGE = OUT / "stage"; STAGE.mkdir(exist_ok=True)
shutil.copy(OUT / "dex" / "classes.dex", STAGE / "classes.dex")
shutil.copytree(PROJ / "META-INF", STAGE / "META-INF", dirs_exist_ok=True)
with zipfile.ZipFile(OUT / "unsigned.apk", "a") as z:
    z.write(STAGE / "classes.dex", "classes.dex", compress_type=zipfile.ZIP_DEFLATED)
    for root, _, files in os.walk(STAGE / "META-INF"):
        for f in sorted(files):
            full = os.path.join(root, f)
            z.write(full, os.path.relpath(full, STAGE), compress_type=zipfile.ZIP_DEFLATED)

print("[5/7] zipalign")
run([str(BT / "zipalign.exe"), "-f", "-p", "4", str(OUT / "unsigned.apk"), str(OUT / "aligned.apk")])

print("[6/7] sign")
KS = PROJ / "debug.keystore"
if not KS.exists():
    run([shutil.which("keytool"), "-genkeypair", "-keystore", str(KS),
         "-storepass", "android", "-keypass", "android", "-alias", "androiddebugkey",
         "-keyalg", "RSA", "-validity", "10000",
         "-dname", "CN=Android Debug,O=Android,C=US"])
FINAL = PROJ / f"LiquidGlass-v{VERSION}.apk"
run([JAVA, "-cp", str(BT / "lib" / "apksigner.jar"), "com.android.apksigner.ApkSignerTool",
     "sign", "--ks", str(KS), "--ks-pass", "pass:android", "--key-pass", "pass:android",
     "--out", str(FINAL), str(OUT / "aligned.apk")])

print("[7/7] verify")
run([JAVA, "-cp", str(BT / "lib" / "apksigner.jar"), "com.android.apksigner.ApkSignerTool",
     "verify", "--print-certs", str(FINAL)])
print("BUILT:", FINAL, FINAL.stat().st_size, "bytes")
