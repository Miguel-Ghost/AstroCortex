> Dentro de AstroCortex este paquete es la carpeta `Motor/`: los scripts `instalar.sh`, `ejecutar_todo.sh`, `ver_estado.sh` y `empaquetar_salidas.sh` están en `Motor/scripts/` y se ejecutan desde `Motor/` (por ejemplo `scripts/ejecutar_todo.sh --modelos`).

# Conexión a la máquina Vast por SSH

Brian alquila la máquina y pasa tres datos: **IP**, **puerto SSH** y el acceso. Abajo, `IP` y `PUERTO` son esos valores. Todo el trabajo se hace en `/workspace`.

## 1. Acceso: clave propia (recomendado)

Lo más seguro es que cada uno use su propia clave y que no circule la clave privada de nadie.

1. En la PC de Miguel (Windows, PowerShell):
   ```powershell
   ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\vast_miguel
   Get-Content $env:USERPROFILE\.ssh\vast_miguel.pub
   ```
2. La línea que imprime el segundo comando (empieza con `ssh-ed25519`) es la clave **pública**. Esa se manda a Brian.
3. Brian la agrega en la máquina con una de estas dos opciones:
   - en la consola de Vast, en las claves SSH de la instancia;
   - en una sesión SSH suya: `echo "ssh-ed25519 AAAA... miguel" >> ~/.ssh/authorized_keys`.

Si Brian manda un archivo de clave privada, se guarda en `C:\Users\<usuario>\.ssh\` y se usa con `-i`, como en el punto 2. Ese archivo no se reenvía ni se sube al Drive.

## 2. Conectarse

Windows (PowerShell; OpenSSH viene instalado) o Ubuntu:

```bash
ssh -i ~/.ssh/vast_miguel -p PUERTO root@IP -L 8888:localhost:8888
```

En Windows, la ruta de la clave es `$env:USERPROFILE\.ssh\vast_miguel`. La parte `-L 8888:localhost:8888` abre el túnel para Jupyter (punto 5). Si es la primera vez, ssh pregunta si se confía en la máquina: se responde `yes`.

## 3. Bajar el paquete a la máquina

**Opción A: desde el Drive.** El enlace tiene que estar como "cualquier persona con el enlace".

```bash
cd /workspace
python3 -m pip install --user -q gdown
~/.local/bin/gdown --fuzzy "ENLACE_DEL_DRIVE" -O CLASIFICADOR_VAST.zip
unzip -q CLASIFICADOR_VAST.zip && cd CLASIFICADOR_VAST && chmod +x *.sh
```

**Opción B: desde la PC, por scp.** Se ejecuta en PowerShell, no en la máquina:

```powershell
scp -i $env:USERPROFILE\.ssh\vast_miguel -P PUERTO CLASIFICADOR_VAST.zip root@IP:/workspace/
```

Después se sigue el LEEME, sección 2: `./instalar.sh` y luego tmux.

## 4. tmux: que nada se corte si se cae la conexión

| Acción | Teclas o comando |
|---|---|
| crear sesión | `tmux new -s clasificador` |
| nueva ventana | Ctrl+b y luego c |
| cambiar de ventana | Ctrl+b y luego 0, 1, 2… |
| salir sin cortar nada | Ctrl+b y luego d |
| volver a la sesión | `tmux attach -t clasificador` |
| ver el avance desde fuera | `cd /workspace/CLASIFICADOR_VAST && ./ver_estado.sh` |

## 5. Jupyter (para los notebooks)

En una ventana de tmux:

```bash
cd /workspace/CLASIFICADOR_VAST && source .venv/bin/activate
jupyter lab --no-browser --ip 127.0.0.1 --port 8888
```

Jupyter imprime una dirección con `token=...`. Con la conexión del punto 2 abierta, esa dirección se abre en el navegador de la PC como `http://localhost:8888/lab?token=...`. Los notebooks están en `notebooks/` y usan el kernel "Clasificador (.venv)".

## 6. Devolver los resultados

```bash
cd /workspace/CLASIFICADOR_VAST && ./empaquetar_salidas.sh
```

Desde la PC (PowerShell):

```powershell
scp -i $env:USERPROFILE\.ssh\vast_miguel -P PUERTO root@IP:/workspace/CLASIFICADOR_VAST/ENTREGA_CLASIFICADOR_*.zip .
```

Ese zip va al Drive del equipo o directo a Brian.

## 7. Al terminar

La máquina cobra por hora mientras está encendida, y al destruirla se borra `/workspace`. Antes de avisar a Brian para que la detenga o la destruya, hay que confirmar que el zip de resultados ya está en la PC o en el Drive.
