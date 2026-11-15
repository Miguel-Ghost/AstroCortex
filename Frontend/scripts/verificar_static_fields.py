#!/usr/bin/env python3
"""Valida manifests y bytes originales de SPHEREx; no necesita bibliotecas externas."""
from pathlib import Path
import json, struct, math, sys

ROOT=Path(__file__).resolve().parent.parent/'public'/'static'/'fields'
assert ROOT.is_dir(), f'No existe {ROOT}'
errors=[]; frames=0
manifests=sorted(ROOT.glob('*/manifest.json'))
for p in manifests:
    try:
        m=json.loads(p.read_text(encoding='utf-8'))
        assert m['target_id']==p.parent.name
        assert m['nx']==31 and m['ny']==31
        seen=set()
        for e in m['epochs']:
            for f in e['frames']:
                k=(e['epoch_id'],f['detector'])
                if k in seen: raise ValueError(f'Duplicado {k}')
                seen.add(k)
                for key in ('image_url','data_url','flags_url'):
                    url=f[key]
                    if not url.startswith('/static/fields/'):
                        raise ValueError(f'URL no es /static/fields: {url}')
                    local=ROOT/url.removeprefix('/static/fields/')
                    if not local.is_file(): raise FileNotFoundError(local)
                data=ROOT/f['data_url'].removeprefix('/static/fields/')
                if data.stat().st_size!=m['nx']*m['ny']*4: raise ValueError(f'BIN tamaño incorrecto: {data}')
                # Confirmar little-endian float32 parseable; NaN permitido.
                with data.open('rb') as binf:
                    values=struct.unpack('<'+('f'*(m['nx']*m['ny'])), binf.read())
                if not any(math.isfinite(v) for v in values):
                    raise ValueError(f'Todos los valores no finitos: {data}')
                frames+=1
        print(f"PASS {m['target_id']}: {len(m['epochs'])} epochs, {len(seen)} frames")
    except Exception as ex:
        errors.append(f'{p}: {ex}')
if len(manifests)!=5:errors.append(f'Se esperaban 5 manifiestos; hallados {len(manifests)}')
if frames!=94:errors.append(f'Se esperaban 94 frames; hallados {frames}')
if errors:
    print('FAIL:\n'+'\n'.join(errors), file=sys.stderr);sys.exit(1)
print(f'OK: {len(manifests)} manifests; {frames} complete frames; all paths and BIN verified.')
