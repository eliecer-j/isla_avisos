# Isla de Avisos

App de escritorio para Windows que avisa **con antelación** de los vencimientos
que se acercan (pensada para RRHH/nómina: contratos que caducan), con un aviso
flotante tipo *Dynamic Island*: una "isla" arriba en el centro de la pantalla que
se abre sola y **muestra el contenido del aviso**.

Las fechas se leen de un archivo **Excel** (solo lectura). La app vigila el archivo
y se actualiza sola cuando lo guardas.

---

## Para el usuario final (instalación)

1. Ejecuta `IslaAvisos-Setup-0.1.0.exe` y sigue el asistente.
   - Se instala **solo para tu usuario** (`%LOCALAPPDATA%\Programs\Isla de Avisos`),
     **sin pedir administrador**.
   - Puedes marcar *acceso directo en el escritorio* y *arrancar con Windows*.
2. Al abrir por primera vez se abre solo el diálogo de **Configuración**: elige tu
   Excel y confirma las columnas.
3. La app queda en la **bandeja del sistema** (junto al reloj).

> El `.exe` no está firmado digitalmente, así que Windows SmartScreen puede avisar
> la primera vez: *Más información → Ejecutar de todas formas*.

### Versión portable

`IslaAvisos-Portable.exe` es un único archivo que se puede llevar en un USB.
Guarda la configuración y el log **junto al ejecutable** (carpeta
`IslaAvisos-data`), sin tocar `%APPDATA%`.

---

## El aviso

Cuando una tarea se acerca al umbral (15 días, 7 días, 2 días o el vencimiento),
la isla se abre y muestra el mensaje, por ejemplo:

> **Juan Pérez: Contrato temporal vence el 05/11/2026 (en 15 días)**

Debajo aparecen dos botones:

| Botón        | Qué hace                                                            |
|--------------|---------------------------------------------------------------------|
| **Entendido**| Descarta **ese** umbral. No vuelve a insistir hasta el siguiente.    |
| **Posponer** | Silencia el aviso 1 hora (configurable).                             |

Si no descartas, la app **insiste**: por defecto hasta **3 veces al día**, con al
menos **4 horas** entre avisos y solo entre las **08:00 y las 20:00**. El contador
se reinicia cada día. Todo eso se cambia en *Configuración*.

La descripción del aviso se arma con una **plantilla** que puedes editar:

```
{titulo} · {detalle} · {notas}: {accion} el {fecha} (en {dias} días)
```

Marcadores disponibles: `{titulo}` `{detalle}` `{fecha}` `{hora}` `{dias}`
`{prioridad}` `{notas}` `{accion}` `{motivo}`. Si un campo está vacío (por
ejemplo `Detalle`), se limpia el hueco automáticamente.

`{accion}` es el verbo del aviso: **`vence contrato`** para el vencimiento del
contrato y **`notificar vencimiento`** para la fecha de notificación (ver más
abajo).

---

## Estructura del Excel

Fila de encabezados (por defecto la 1; en planillas con un título arriba, la 2).
La app **detecta** las columnas y tú confirmas el mapeo, así que los nombres
pueden variar. Columnas reconocidas:

| Columna               | ¿Obligatoria? | Contenido                                                     |
|-----------------------|---------------|---------------------------------------------------------------|
| Tarea                 | Sí            | Nombre / título (p. ej. el empleado)                          |
| Fecha                 | Sí            | Vencimiento: celda de fecha, `dd/mm/aaaa`, `aaaa-mm-dd` o escrita a mano en español (`11 de diciembre de 2025`) |
| Detalle               | No            | Tipo de contrato, área, categoría… (sale en el aviso)          |
| Fecha de notificación | No            | Genera un **aviso extra** ese día (ver abajo)                 |
| Hora                  | No            | `HH:MM` (si falta, se asume fin del día)                      |
| Notas                 | No            | Texto libre (p. ej. la vigencia del contrato)                  |
| Prioridad             | No            | Baja / Media / Alta / Crítica                                 |
| Estado                | No            | Marca la tarea como hecha (`hecha`, `x`, `sí`, `done`…)        |

Puedes probar el mapeo con el botón **Probar lectura** del diálogo de
configuración: dice cuántas tareas detecta y muestra una vista previa real.

Las celdas `N/A`, `-`, `PENDIENTE` o vacías se consideran "sin vencimiento" (no
avisan). Con la opción **Ocultar lo que ya ha vencido** activada, las fechas
pasadas no aparecen ni generan avisos.

### Fecha de notificación (segundo aviso)

Si mapeas esta columna, cada contrato produce **dos avisos** independientes:

- **Vencimiento del contrato**, cuando se acerca la fecha de vencimiento:
  `JUAN PÉREZ · PRODUCCION · 5 MESES: vence contrato el 30/10/2026 (en 2 días)`
- **Notificación al empleado**, cuando llega el día de avisarle:
  `JUAN PÉREZ · PRODUCCION · 5 MESES: notificar vencimiento el 15/09/2026 (en 2 días)`

Cada uno usa las mismas anticipaciones (15 / 7 / 2 días por defecto) y se
descarta o pospone por separado, así que avisar de uno no silencia al otro.
Si dejas la columna en `(ninguna)`, solo existe el aviso de vencimiento.
Las fechas de notificación ya pasadas se ocultan igual que las de vencimiento.

---

## Uso de la isla

- **Clic** en cualquier parte de la isla: expandir / plegar.
- **Botón ✕** (cabecera): plegar la isla a su forma compacta.
- **Botón —** (cabecera): **quitar la isla de la pantalla** (la app sigue en la
  bandeja). Para que vuelva: clic derecho en la bandeja → *Mostrar isla*, o doble
  clic en el icono. Si hay un aviso nuevo, la isla reaparece sola.
- **Arrastrar**: mover la isla (se recuerda la posición).
- **Hover**: mantiene la isla abierta.
- La altura al expandirse se ajusta al número de tareas (sin cajas vacías).
- **Aspecto**: negro opaco, como la Dynamic Island real (nada de transparencias) y
  con los colores del sistema iOS en modo oscuro. Al abrir se expande en 0,4 s con
  un rebote mínimo y el contenido entra con un fundido; al plegarse tarda 0,26 s.
- **Bandeja** (clic derecho): mostrar/ocultar, recentrar, recargar, pausar,
  configuración, abrir Excel, iniciar con Windows, salir.

Una sola instancia: si abres la app dos veces, la segunda no duplica nada y trae
al frente la que ya está en marcha.

---

## Desarrollo

### Ejecutar desde el código

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Excel de pruebas (datos de ejemplo tipo nómina)
.\.venv\Scripts\python.exe tools\create_test_excel.py

.\.venv\Scripts\python.exe main.py
```

### Compilar la aplicación

```powershell
.\build.ps1              # icono + .exe (carpeta) + portable + instalador
.\build.ps1 -SkipSetup   # solo los .exe, sin instalador
.\build.ps1 -Clean       # borra dist/ antes de compilar
```

El script crea el entorno, instala `pyinstaller` y `pillow`, genera
`assets/isla_avisos.ico`, compila los dos `.spec` e invoca Inno Setup (lo instala
con `winget` si no está). Resultado en `dist\`:

```
dist\Isla de Avisos\Isla de Avisos.exe     App en carpeta (la que usa el instalador)
dist\IslaAvisos-Portable.exe               Version portable (un solo archivo)
dist\IslaAvisos-Setup-0.1.0.exe            Instalador con desinstalador
```

---

## Estructura del proyecto

```
main.py                        Arranque, estilo, instancia unica y primer arranque
app/paths.py                   Rutas de config/log, recursos y modo portable
app/config.py                  Configuración en %APPDATA%\IslaAvisos\config.json
app/models.py                  Tarea, prioridad, cuentas atrás y plantilla del mensaje
app/excel_source.py            Lectura del Excel y detección de cambios
app/reminder_engine.py         Umbrales e insistencia hasta descartar
app/island_window.py           Ventana tipo Dynamic Island y banner del aviso
app/config_dialog.py           Diálogo de configuración
app/tray.py                    Icono y menú de la bandeja
app/autostart.py               Arranque con Windows (registro HKCU)
app/single_instance.py         Una sola instancia (named pipe)
app/logsetup.py                Log de diagnóstico rotado
app/sound.py                   Sonido de aviso
app/theme.py                   Icono y estilos
tools/create_test_excel.py     Generador del Excel de pruebas
tools/make_icon.py             Generador de assets/isla_avisos.ico
isla_avisos.spec               PyInstaller (carpeta)
isla_avisos_portable.spec      PyInstaller (un solo archivo)
installer/isla_avisos.iss      Instalador Inno Setup
build/version_info.txt         Metadatos del .exe (Propiedades)
build.ps1                      Compila todo
```

### Diagnóstico

Si algo falla, revisa `%APPDATA%\IslaAvisos\isla.log` (o
`IslaAvisos-data\isla.log` en la versión portable).
