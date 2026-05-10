import json, pathlib

nb_path = pathlib.Path(r'C:\Users\jlalo\Curso_Data\Proyecto-ML\api.ipynb')
nb = json.loads(nb_path.read_bytes())

fixed = 0
for cell in nb['cells']:
    if cell.get('cell_type') != 'code':
        continue
    src = cell['source']
    if not isinstance(src, list):
        continue

    # Fix 1: remove spurious indented 'if _aemet_tramo_en_bd' line after isinstance checks
    new_src = []
    i = 0
    while i < len(src):
        line = src[i]
        if ('fecha_fin = pd.Timestamp(fecha_fin)' in line
                and i + 1 < len(src)
                and 'if _aemet_tramo_en_bd(nombre, ini_dt, fin_dt):' in src[i + 1]
                and i + 2 < len(src)
                and '_init_aemet_db()' in src[i + 2]):
            new_src.append(line)
            # skip the spurious line at i+1, keep _init_aemet_db at i+2
            i += 2
            fixed += 1
            print('Fix 1 applied: removed spurious if line')
        else:
            new_src.append(line)
            i += 1
    cell['source'] = new_src
    src = new_src

    # Fix 2: reorder scrambled plot lines
    for j, line in enumerate(src):
        if "axes[1].set_ylabel(" in line and j + 1 < len(src) and 'plt.show()' in src[j + 1]:
            new_tail = [
                "    axes[1].set_ylabel('Precipitaci\u00f3n (mm)')\n",
                "    axes[1].set_xlabel('Fecha')\n",
                "    axes[1].tick_params(axis='x', rotation=45)\n",
                "\n",
                "    plt.tight_layout()\n",
                "    plt.show()\n",
            ]
            cell['source'] = src[:j] + new_tail
            fixed += 1
            print('Fix 2 applied: reordered plot lines')
            break

print(f'Total fixes applied: {fixed}')
nb_path.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding='utf-8')
print('Saved.')
