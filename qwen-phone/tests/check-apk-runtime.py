"""Reject APK native dependencies unavailable to a standalone application child."""
import io,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/elftools'))
from elftools.elf.elffile import ELFFile
apk=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'build/qwen-local-beta.apk'
platform={'libc.so','libm.so','libdl.so','liblog.so','libandroid.so','libz.so'}
with zipfile.ZipFile(apk) as z:
    libraries={Path(n).name:n for n in z.namelist() if n.startswith('lib/arm64-v8a/') and n.endswith('.so')}
    assert 'libqwen-server.so' in libraries
    assert any(n.startswith('libggml-cpu-') for n in libraries)
    for name,entry in libraries.items():
        elf=ELFFile(io.BytesIO(z.read(entry)))
        needed={t.needed for t in elf.get_section_by_name('.dynamic').iter_tags() if t.entry.d_tag=='DT_NEEDED'}
        missing=needed-set(libraries)-platform
        assert not missing, f'{name}: unresolved app dependency {missing}'
print('APK_RUNTIME_DEPENDENCIES_OK: no undeclared vendor library dependencies')
