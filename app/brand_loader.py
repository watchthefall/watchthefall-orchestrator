import os
import glob
import yaml
import re
import shutil
from typing import Dict, List, Optional
from fnmatch import fnmatch

try:
    # When imported as a module
    from .config import IMPORTS_BRANDS_DIR
except ImportError:
    # When executed as a script: python app/brand_loader.py
    import sys as _sys
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, '..'))
    if _PROJECT_ROOT not in _sys.path:
        _sys.path.insert(0, _PROJECT_ROOT)
    from app.config import IMPORTS_BRANDS_DIR

def _safe_yaml_load(path: str) -> Optional[dict]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return None

def _find_first(patterns: List[str]) -> Optional[str]:
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    return None

def _scan_brand_dir(brand_dir: str) -> Dict:
    """
    Scan a brand directory to discover assets and optional manifests.
    Returns a brand config dict.
    """
    brand_name = os.path.basename(brand_dir)

    # Load manifest files if available
    manifest = {}
    # Common manifest filenames
    for mf in ['manifest.yml', 'brand.yml', f'{brand_name}.yml', 'brands.yml']:
        mf_path = os.path.join(brand_dir, mf)
        if os.path.isfile(mf_path):
            data = _safe_yaml_load(mf_path)
            if data:
                manifest.update(data)

    # Watermark manifest
    watermark_manifest = {}
    for wf in ['watermark.yml', 'watermark.yaml']:
        wf_path = os.path.join(brand_dir, wf)
        if os.path.isfile(wf_path):
            data = _safe_yaml_load(wf_path)
            if data:
                watermark_manifest.update(data)

    # Orientation rules
    orientation_rules = None
    for orf in ['orientation.yml', 'orientation.yaml', 'orientation_rules.yml', 'orientation_rules.yaml']:
        orf_path = os.path.join(brand_dir, orf)
        if os.path.isfile(orf_path):
            data = _safe_yaml_load(orf_path)
            if data:
                orientation_rules = data
                break

    # Discover assets by filename conventions; do not rename or modify
    template_png = _find_first([
        os.path.join(brand_dir, '*template*.png'),
        os.path.join(brand_dir, 'template.png')
    ])
    watermark_png = _find_first([
        os.path.join(brand_dir, '*watermark*.png'),
        os.path.join(brand_dir, 'watermark.png')
    ])
    logo_png = _find_first([
        os.path.join(brand_dir, '*logo*.png'),
        os.path.join(brand_dir, 'logo.png')
    ])

    # Glitch overlays - DISABLED: posters moved to assets/posters/
    # Only detect overlays from wtf_orchestrator/glitch/ if it exists
    # Ignore files in assets/posters/ and any poster-like files
    glitch_overlays = []
    # INTENTIONALLY LEFT EMPTY - no glitch overlays used in video processing

    # Routing/platforms manifests (optional)
    routing_yml = _find_first([os.path.join(brand_dir, 'routing.yml')])
    platforms_yml = _find_first([os.path.join(brand_dir, 'platforms.yml')])

    # Position defaults; can be overridden by manifest files
    watermark_position = (
        watermark_manifest.get('position') or
        manifest.get('watermark_position') or
        'bottom-right'
    )
    wm_scale = (
        watermark_manifest.get('scale') or
        manifest.get('watermark_scale') or
        0.25  # relative scale against video width
    )

    display_name = manifest.get('display_name') or brand_name

    return {
        'name': brand_name,
        'display_name': display_name,
        'assets': {
            'template': template_png,
            'watermark': watermark_png,
            'logo': logo_png,
            'glitch_overlays': glitch_overlays
        },
        'manifests': {
            'manifest': manifest if manifest else None,
            'watermark_manifest': watermark_manifest if watermark_manifest else None,
            'routing': routing_yml,
            'platforms': platforms_yml,
            'orientation_rules': orientation_rules
        },
        'options': {
            'watermark_position': watermark_position,
            'watermark_scale': wm_scale
        }
    }

def _load_top_level_brands_yml() -> Optional[Dict[str, Dict]]:
    """
    If imports/brands/brands.yml exists, use it to define brands and assets.
    """
    top_yml = os.path.join(IMPORTS_BRANDS_DIR, 'brands.yml')
    if os.path.isfile(top_yml):
        data = _safe_yaml_load(top_yml)
        if not data:
            return None
        # Normalize structure: expect mapping of brand_name -> config
        brands_cfg = {}
        for brand_name, cfg in (data.items() if isinstance(data, dict) else []):
            brand_dir = os.path.join(IMPORTS_BRANDS_DIR, brand_name)
            if not os.path.isdir(brand_dir):
                # Still register even if directory is missing, but assets must be absolute paths in cfg
                pass
            # Merge directory scan results with provided config
            scanned = _scan_brand_dir(brand_dir) if os.path.isdir(brand_dir) else {'name': brand_name, 'assets': {}, 'options': {}}
            # Apply overrides from cfg; keep filenames identical
            assets = scanned.get('assets', {}).copy()
            cfg_assets = cfg.get('assets', {}) if isinstance(cfg, dict) else {}
            for k, v in cfg_assets.items():
                if isinstance(v, str) and v.strip():
                    assets[k] = v
            options = scanned.get('options', {}).copy()
            cfg_opts = cfg.get('options', {}) if isinstance(cfg, dict) else {}
            options.update({k: v for k, v in cfg_opts.items() if v is not None})
            brands_cfg[brand_name] = {
                'name': brand_name,
                'display_name': cfg.get('display_name') or scanned.get('display_name') or brand_name,
                'assets': assets,
                'options': options,
                'manifests': scanned.get('manifests', {})
            }
        return brands_cfg
    return None

def get_brands() -> List[Dict]:
    """
    Returns a list of brand configurations discovered in imports/brands.
    """
    # Prefer top-level brands.yml if present
    top_cfg = _load_top_level_brands_yml()
    if top_cfg:
        return list(top_cfg.values())

    # Otherwise, discover brand directories
    brands = []
    for entry in sorted(os.listdir(IMPORTS_BRANDS_DIR)):
        brand_dir = os.path.join(IMPORTS_BRANDS_DIR, entry)
        if os.path.isdir(brand_dir):
            brands.append(_scan_brand_dir(brand_dir))
    return brands

# ============================================================================
# ASSET IMPORTER FUNCTIONS
# ============================================================================

def _slug_name(name: str) -> str:
    s = re.sub(r'[^a-zA-Z0-9_-]+', '-', name.strip())
    s = s.lower().strip('-')
    return s or 'brand'

def _dir_contains_patterns(dir_path: str, patterns: List[str]) -> bool:
    try:
        for fname in os.listdir(dir_path):
            for p in patterns:
                if fnmatch(fname.lower(), p):
                    return True
    except Exception:
        return False
    return False

def _find_files(dir_path: str, patterns: List[str]) -> List[str]:
    matches = []
    try:
        for root, _, files in os.walk(dir_path):
            for f in files:
                fl = f.lower()
                if any(fnmatch(fl, pat) for pat in patterns):
                    matches.append(os.path.join(root, f))
    except Exception:
        pass
    return sorted(set(matches))

def _is_brand_dir(dir_path: str) -> bool:
    name = os.path.basename(dir_path).lower()
    
    # IGNORE: Android/Gradle build artifacts
    ignore_patterns = [
        'wtf-',  # wtf-1, wtf-2, etc. are build artifacts
        '.cxx',
        'cmake',
        'build',
        'debug',
        'release',
        'intermediates',
        'node_modules',
        'drawable-',  # Android drawables
    ]
    
    for pattern in ignore_patterns:
        if pattern in name:
            return False
    
    png_present = _dir_contains_patterns(dir_path, ['*template*.png', '*watermark*.png', '*logo*.png'])
    yaml_present = _dir_contains_patterns(dir_path, ['*.yml', '*.yaml'])
    name_match = ('wtf' in name) or re.search(r'(europwtf|scotlandwtf|usw)$', name or '') is not None
    in_brands_path = ('assets{}brands'.format(os.sep) in dir_path.lower()) or (f'{os.sep}brands' in dir_path.lower())
    return png_present or yaml_present or name_match or in_brands_path

def _collect_brand_candidates(source_root: str) -> Dict[str, Dict]:
    candidates: Dict[str, Dict] = {}
    print(f"Scanning source directory: {source_root}")
    for root, dirs, files in os.walk(source_root):
        base = os.path.basename(root)
        if base.startswith('.') or base.lower() in ('node_modules', '__pycache__'):
            continue
        if _is_brand_dir(root):
            brand_name = _slug_name(base)
            suffix = 1
            unique_name = brand_name
            while unique_name in candidates and candidates[unique_name]['source_dir'] != root:
                suffix += 1
                unique_name = f'{brand_name}-{suffix}'
            candidates[unique_name] = {'name': unique_name, 'source_dir': root}
            print(f"  Found brand candidate: {unique_name} at {root}")
    return candidates

def _copy_preserve(src: str, dest_dir: str, report: Dict) -> Optional[str]:
    try:
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, os.path.basename(src))
        if os.path.exists(dest_path):
            report['skipped_existing'].append(dest_path)
            return dest_path
        shutil.copy2(src, dest_path)
        report['copied'].append(dest_path)
        return dest_path
    except Exception as e:
        report['errors'].append(f'Copy failed: {src} -> {dest_dir}: {e}')
        return None

def _generate_minimal_files(brand_dir: str, has_template: bool, has_watermark: bool, has_logo: bool, report: Dict):
    manifest_path = os.path.join(brand_dir, 'manifest.yml')
    watermark_path = os.path.join(brand_dir, 'watermark.yml')
    orientation_path = os.path.join(brand_dir, 'orientation.yml')

    if not os.path.exists(manifest_path) and (has_template or has_watermark or has_logo):
        data = {
            'display_name': os.path.basename(brand_dir),
            'watermark_position': 'bottom-right',
            'watermark_scale': 0.25
        }
        try:
            with open(manifest_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(data, f, sort_keys=False)
            report['generated'].append(manifest_path)
        except Exception as e:
            report['errors'].append(f'Generate manifest.yml failed: {e}')

    if not os.path.exists(watermark_path) and has_watermark:
        data = {'position': 'bottom-right', 'scale': 0.25}
        try:
            with open(watermark_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(data, f, sort_keys=False)
            report['generated'].append(watermark_path)
        except Exception as e:
            report['errors'].append(f'Generate watermark.yml failed: {e}')

    if not os.path.exists(orientation_path):
        data = {'rules': [{'match': '*', 'orientation': 'auto'}]}
        try:
            with open(orientation_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(data, f, sort_keys=False)
            report['generated'].append(orientation_path)
        except Exception as e:
            report['errors'].append(f'Generate orientation.yml failed: {e}')

def _build_brands_yml_if_absent(brands_info: Dict[str, Dict]):
    top_yml = os.path.join(IMPORTS_BRANDS_DIR, 'brands.yml')
    if os.path.exists(top_yml):
        print(f"brands.yml already exists at {top_yml}, skipping generation")
        return
    data = {}
    for bname, info in brands_info.items():
        assets = {}
        if info.get('template'):
            assets['template'] = os.path.relpath(info['template'], os.path.dirname(top_yml)).replace('\\', '/')
        if info.get('watermark'):
            assets['watermark'] = os.path.relpath(info['watermark'], os.path.dirname(top_yml)).replace('\\', '/')
        if info.get('logo'):
            assets['logo'] = os.path.relpath(info['logo'], os.path.dirname(top_yml)).replace('\\', '/')
        if info.get('glitch_overlays'):
            assets['glitch_overlays'] = [os.path.relpath(p, os.path.dirname(top_yml)).replace('\\', '/') for p in info['glitch_overlays']]
        entry = {
            'display_name': info.get('display_name') or bname,
            'assets': assets,
            'options': {
                'watermark_scale': 0.25,
                'watermark_position': 'bottom-right'
            }
        }
        if info.get('orientation_yml'):
            entry['manifests'] = {'orientation_rules': os.path.relpath(info['orientation_yml'], os.path.dirname(top_yml)).replace('\\', '/')}
        data[bname] = entry
    try:
        with open(top_yml, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f, sort_keys=False)
        print(f"Generated brands.yml at {top_yml}")
    except Exception as e:
        print(f"Failed to generate brands.yml: {e}")

def import_assets(source_root: str) -> str:
    print(f"\n{'='*70}")
    print(f"WATCHTHEFALL ORCHESTRATOR V2 - ASSET IMPORTER")
    print(f"{'='*70}\n")
    
    if not os.path.exists(source_root):
        return f"[ASSET_IMPORT_SUMMARY]\nERROR: Source path does not exist: {source_root}\n[/ASSET_IMPORT_SUMMARY]"
    
    candidates = _collect_brand_candidates(source_root)
    print(f"\nFound {len(candidates)} brand candidate(s)\n")
    
    results = {}
    summary_lines = []
    
    for bname, cand in candidates.items():
        print(f"Processing brand: {bname}")
        src_dir = cand['source_dir']
        dest_dir = os.path.join(IMPORTS_BRANDS_DIR, bname)
        os.makedirs(dest_dir, exist_ok=True)
        rep = {'copied': [], 'skipped_existing': [], 'generated': [], 'errors': []}

        templates = _find_files(src_dir, ['*template*.png'])
        watermarks = _find_files(src_dir, ['*watermark*.png'])
        logos = _find_files(src_dir, ['*logo*.png'])
        glitches = _find_files(src_dir, ['*glitch*.png'])
        glitch_dirs = []
        for sub in ('glitch', 'overlays', 'glitches'):
            gdir = os.path.join(src_dir, sub)
            if os.path.isdir(gdir):
                glitch_dirs.extend(sorted(_find_files(gdir, ['*.png'])))
        if glitch_dirs:
            glitches = sorted(set(glitches + glitch_dirs))

        manifest_files = _find_files(src_dir, ['manifest.yml', 'manifest.yaml', 'brand.yml', 'brands.yml', 'watermark.yml', 'watermark.yaml', 'orientation.yml', 'orientation.yaml', 'routing.yml', 'platforms.yml'])

        chosen_template = None
        chosen_watermark = None
        chosen_logo = None

        for p in templates:
            dp = _copy_preserve(p, dest_dir, rep)
            if not chosen_template and dp:
                chosen_template = dp
        for p in watermarks:
            dp = _copy_preserve(p, dest_dir, rep)
            if not chosen_watermark and dp:
                chosen_watermark = dp
        for p in logos:
            dp = _copy_preserve(p, dest_dir, rep)
            if not chosen_logo and dp:
                chosen_logo = dp

        glitch_dest = os.path.join(dest_dir, 'glitch')
        for p in glitches:
            _copy_preserve(p, glitch_dest, rep)

        orientation_yml = None
        for p in manifest_files:
            base = os.path.basename(p).lower()
            dp = _copy_preserve(p, dest_dir, rep)
            if dp and base in ('orientation.yml', 'orientation.yaml'):
                orientation_yml = dp

        _generate_minimal_files(dest_dir, bool(chosen_template), bool(chosen_watermark), bool(chosen_logo), rep)
        if not orientation_yml and os.path.exists(os.path.join(dest_dir, 'orientation.yml')):
            orientation_yml = os.path.join(dest_dir, 'orientation.yml')

        display_name = os.path.basename(dest_dir)
        glitch_out = sorted(_find_files(glitch_dest, ['*.png'])) if os.path.isdir(glitch_dest) else []

        results[bname] = {
            'name': bname,
            'source_dir': src_dir,
            'dest_dir': dest_dir,
            'template': chosen_template,
            'watermark': chosen_watermark,
            'logo': chosen_logo,
            'glitch_overlays': glitch_out,
            'orientation_yml': orientation_yml,
            'display_name': display_name,
            'manifests_present': sorted([os.path.basename(p) for p in _find_files(dest_dir, ['*.yml', '*.yaml'])]),
            'report': rep
        }
        
        print(f"  ✓ Copied {len(rep['copied'])} files")
        print(f"  ✓ Skipped {len(rep['skipped_existing'])} existing files")
        print(f"  ✓ Generated {len(rep['generated'])} manifest files")
        if rep['errors']:
            print(f"  ⚠ {len(rep['errors'])} errors")

    print(f"\nBuilding brands.yml...")
    _build_brands_yml_if_absent(results)

    print(f"\nGenerating integrity report...\n")
    for bname, info in results.items():
        t_ok = 'yes' if info.get('template') else 'no'
        w_ok = 'yes' if info.get('watermark') else 'no'
        l_ok = 'yes' if info.get('logo') else 'no'
        glitches_count = len(info.get('glitch_overlays') or [])
        manifests = ', '.join(info.get('manifests_present') or [])
        missing = []
        if t_ok == 'no': missing.append('template.png')
        if w_ok == 'no': missing.append('watermark.png')
        if l_ok == 'no': missing.append('logo.png')
        suspicious = []
        try:
            for f in os.listdir(info['dest_dir']):
                if os.path.isfile(os.path.join(info['dest_dir'], f)):
                    fl = f.lower()
                    if not (fl.endswith('.png') or fl.endswith('.yml') or fl.endswith('.yaml')):
                        suspicious.append(f)
        except Exception:
            pass

        summary_lines.append(f'Brand: {bname}')
        summary_lines.append(f'  Source: {info["source_dir"]}')
        summary_lines.append(f'  Destination: {info["dest_dir"]}')
        summary_lines.append(f'  template found: {t_ok}')
        summary_lines.append(f'  watermark found: {w_ok}')
        summary_lines.append(f'  logo found: {l_ok}')
        summary_lines.append(f'  glitch overlays: {glitches_count}')
        summary_lines.append(f'  manifests present: {manifests if manifests else "none"}')
        summary_lines.append(f'  missing recommended: {", ".join(missing) if missing else "none"}')
        summary_lines.append(f'  suspicious files: {", ".join(suspicious) if suspicious else "none"}')
        errs = info['report'].get('errors') or []
        summary_lines.append(f'  errors: {", ".join(errs) if errs else "none"}')
        
        # Warnings
        if missing:
            summary_lines.append(f'  ⚠ WARNING: Missing {", ".join(missing)}')
        if t_ok == 'no' and w_ok == 'no' and l_ok == 'no':
            summary_lines.append(f'  ⚠ NEEDS REVIEW: No assets found')
        
        summary_lines.append('')

    try:
        os.makedirs(IMPORTS_BRANDS_DIR, exist_ok=True)
        rpt_path = os.path.join(IMPORTS_BRANDS_DIR, '_integrity_report.txt')
        with open(rpt_path, 'w', encoding='utf-8') as f:
            f.write('[ASSET_IMPORT_SUMMARY]\n')
            f.write('\n'.join(summary_lines).strip() + '\n')
            f.write('[/ASSET_IMPORT_SUMMARY]\n')
        print(f"Integrity report saved to: {rpt_path}\n")
    except Exception as e:
        print(f"Failed to save integrity report: {e}")

    return '[ASSET_IMPORT_SUMMARY]\n' + ('\n'.join(summary_lines).strip() if summary_lines else 'No brands detected.') + '\n[/ASSET_IMPORT_SUMMARY]'

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Import and validate brand assets from old Orchestrator.')
    parser.add_argument('--source', '-s', default=r'C:\Users\Jamie\OneDrive\Desktop\WTF_Orchestrator', help='Source old Orchestrator path')
    args = parser.parse_args()
    summary = import_assets(args.source)
    print(summary)
