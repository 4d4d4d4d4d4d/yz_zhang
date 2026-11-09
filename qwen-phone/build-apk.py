"""Reproducible local private-beta APK build; never stores signing secrets in source."""
from pathlib import Path
import os,shutil,subprocess,sys,zipfile,secrets,hashlib,json,re
if '--keep-vault-unlocked' in sys.argv and '--screen-debug' not in sys.argv:
 raise RuntimeError('--keep-vault-unlocked requires --screen-debug')
R=Path(__file__).resolve().parent
B=R/'build/apk';B.mkdir(parents=True,exist_ok=True)
T=R/'tools/sdk-build/android-15';A=R/'tools/sdk-platform/android-35/android.jar'
J=Path(os.environ.get('QWEN_JAVA_BIN','/Applications/PyCharm.app/Contents/jbr/Contents/Home/bin'))
def run(*a):subprocess.run(list(map(str,a)),check=True)
for name in ('aapt2','zipalign','apksigner','llvm-strip'):
 p=T/name
 if p.exists():p.chmod(0o755)
for d in ('src','classes','dex','assets'):shutil.rmtree(B/d,ignore_errors=True);(B/d).mkdir()
for name in (('PhoneAgent','Vault','Memory','Vision','AgentSkills','SafetyTest') if '--debug' in sys.argv else ('PhoneAgent','Vault','Memory','Vision','AgentSkills')):
 (B/'src'/f'{name}.java').write_text('package org.qwen.local;\n'+(R/'agent'/f'{name}.java').read_text())
for p in (R/'android/src').glob('*.java'):
 if p.name!='BetaInstrumentation.java' or '--debug' in sys.argv:shutil.copy(p,B/'src'/p.name)
page=(R/'agent/index.html').read_text().replace('开发版：AES-256-GCM 加密记录；当前为 ADB shell 服务，尚未迁移到独立 Android 应用与硬件 Keystore。', '内测版：记录以 AES-256-GCM 加密，保存在应用私有目录；口令派生密钥绑定 Android Keystore。硬件保护级别依设备而定。卸载应用或丢失密钥后无法恢复，暂不支持备份。')
(B/'assets/index.html').write_text(page)
shutil.copy(R/'build/runtime/llama-b11527/LICENSE',B/'assets/LLAMA-LICENSE')
if '--debug' in sys.argv:shutil.copy(R/'build/vision-fixture.png',B/'assets/vision-fixture.png')
manifest=(R/'android/AndroidManifest.xml').read_text()
# Explicit, temporary screen inspection build; regular builds retain FLAG_SECURE.
if '--screen-debug' in sys.argv:
 main=B/'src/MainActivity.java'
 source=main.read_text()
 guard='getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);'
 if source.count(guard)!=1:raise RuntimeError('Expected exactly one screen protection guard')
 main.write_text(source.replace(guard,'').replace('小千 · 封闭测试','小千 · 投屏调试（隐私遮挡已关闭）'))
 manifest=manifest.replace('-private-beta','-screen-debug')
 if '--keep-vault-unlocked' in sys.argv:
  source=main.read_text()
  guard='KEEP_VAULT_UNLOCKED_FOR_DEBUG=false'
  if source.count(guard)!=1:raise RuntimeError('Expected exactly one debug vault guard')
  main.write_text(source.replace(guard,'KEEP_VAULT_UNLOCKED_FOR_DEBUG=true'))
  pagefile=B/'assets/index.html'
  pagefile.write_text(pagefile.read_text().replace('已解锁 · 15 分钟无操作后自动锁定','已解锁 · 调试模式，请手动锁定'))
  agent=B/'src/PhoneAgent.java'
  source=agent.read_text()
  if source.count(guard)!=1:raise RuntimeError('Expected exactly one idle vault guard')
  agent.write_text(source.replace(guard,'KEEP_VAULT_UNLOCKED_FOR_DEBUG=true'))
if '--debug' in sys.argv:manifest=manifest.replace('android:debuggable="false"','android:debuggable="true"').replace('</application>','<activity android:name=".BetaInstrumentation$Foreground" android:exported="false" /></application>').replace('</manifest>','<instrumentation android:name=".BetaInstrumentation" android:targetPackage="org.qwen.local" /></manifest>')
(B/'AndroidManifest.xml').write_text(manifest)
run(J/'javac','--release','8','-cp',A,'-d',B/'classes',*sorted((B/'src').glob('*.java')))
run(J/'java','-cp',R/'tools/r8.jar','com.android.tools.r8.D8','--min-api','28','--lib',A,'--output',B/'dex',*sorted((B/'classes/org/qwen/local').glob('*.class')))
run(T/'aapt2','compile','--dir',R/'android/res','-o',B/'resources.zip')
run(T/'aapt2','link','-o',B/'unsigned.apk','--manifest',B/'AndroidManifest.xml','-I',A,'-A',B/'assets',B/'resources.zip')
run(R/'tools/zig/ziglang/zig','cc','-target','aarch64-linux-android','-shared','-nostdlib','-fPIC','-O2','-s',R/'native/app-lifecycle.c','-o',B/'libqwen-lifecycle.so')
runtime=R/'build/runtime/android-cpu/llama-b11527'
libs=['libllama-server-impl.so','libllama-common.so','libmtmd.so','libllama.so','libggml.so','libggml-base.so']+sorted(p.name for p in runtime.glob('libggml-cpu-*.so'))
if not any(name.startswith('libggml-cpu-') for name in libs):raise RuntimeError('Missing Android CPU backends')
with zipfile.ZipFile(B/'unsigned.apk','a',zipfile.ZIP_DEFLATED) as z:
 z.write(B/'dex/classes.dex','classes.dex')
 z.write(B/'libqwen-lifecycle.so','lib/arm64-v8a/libqwen-lifecycle.so')
 for name in libs+['libqwen-server.so']:
  src=runtime/('llama-server' if name=='libqwen-server.so' else name)
  dst=B/name;shutil.copy(src,dst)
  if (T/'llvm-strip').exists():run(T/'llvm-strip','--strip-debug',dst)
  z.write(dst,'lib/arm64-v8a/'+name)
run(T/'zipalign','-f','-P','16','4',B/'unsigned.apk',B/'aligned.apk')
keydir=R/'tools/signing';keydir.mkdir(exist_ok=True);keydir.chmod(0o700)
password=keydir/'beta.pass';keystore=keydir/'beta.p12'
if not password.exists():password.write_text(secrets.token_urlsafe(32));password.chmod(0o600)
if not keystore.exists():
 run(J/'keytool','-genkeypair','-keystore',keystore,'-storetype','PKCS12','-storepass:file',password,'-alias','private-beta','-keyalg','RSA','-keysize','3072','-validity','3650','-dname','CN=Qwen Local Private Beta')
 keystore.chmod(0o600)
output=R/'build'/('qwen-local-screen-debug.apk' if '--screen-debug' in sys.argv else 'qwen-local-debug.apk' if '--debug' in sys.argv else 'qwen-local-beta.apk')
run(J/'java','-jar',T/'lib/apksigner.jar','sign','--v1-signing-enabled','true','--v2-signing-enabled','true','--v3-signing-enabled','true','--ks',keystore,'--ks-pass','file:'+str(password),'--out',output,B/'aligned.apk')
run(J/'java','-jar',T/'lib/apksigner.jar','verify','--verbose',output)
run(T/'zipalign','-c','-P','16','4',output)
with zipfile.ZipFile(output) as package:
 if package.testzip() is not None:raise RuntimeError('APK ZIP corruption')
 if any(name.endswith(('.gguf','.p12','.pass')) or name.endswith('inference.key') for name in package.namelist()):raise RuntimeError('Private signing material or model unexpectedly packaged')
metadata={'artifact':output.name,'version':re.search(r'android:versionName="([^"]+)"',manifest).group(1),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'runtime':'llama.cpp b11527 Android CPU (dynamic CPU variants)','model_included':False,'screen_protection': '--screen-debug' not in sys.argv,'background_vault_lock': '--keep-vault-unlocked' not in sys.argv,'idle_vault_lock': '--keep-vault-unlocked' not in sys.argv,'debuggable':'--debug' in sys.argv,'status':'built; signature, alignment and ZIP integrity verified; device acceptance is recorded separately'}
output.with_suffix('.manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
print(output)
