# WatchDialEdit (CloudFaceCreate)

<img width="1402" height="932" alt="idw13_screenshot" src="https://github.com/user-attachments/assets/c8cf2a79-c97a-4c54-947a-e20d0866504d" />

<img width="1402" height="932" alt="idw20_screenshot" src="https://github.com/user-attachments/assets/ecdf841f-a5fe-4fc3-b80c-95511ae74024" />

An open-source watch face editor for IDO / VeryFit **IWF** watch face files that makes watch face development accessible for everyone.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/) [![PyQt6](https://img.shields.io/badge/UI-PyQt6-41cd52)](https://pypi.org/project/PyQt6/) [![License: GPL v3](https://img.shields.io/badge/License-GPLv3-gray.svg)](https://www.gnu.org/licenses/gpl-3.0)

## Features

* Open existing watch face design folders
* Edit `iwf.json` and `font.json` data
* Add and edit watch face widgets
* Drag, resize, and move items on the canvas
* Grid, snapping, rulers, zoom, and pan
* Multi-selection and keyboard movement
* Undo and redo
* Watch-hand setup with image selection and anchor fields
* Raw property inspector for fields that don't have dedicated controls
* Asset/file picker for image and glyph fields
* Live preview
* Device-specific preview frames where the device profile is known
* Export `.iwf` files locally
* Export preview PNGs
* No web editor or upload is required

## Supported devices

| Device        | Resolution | Hand anchor | Status        |
| ------------- | ---------: | ----------: | ------------- |
| IDW13         |    240×284 |  (120, 142) | Verified      |
| IDW18         |    240×240 |  (120, 120) | Verified      |
| IDW20         |    320×385 |  (160, 193) | Verified      |
| Other devices |          — |           — | Not confirmed |

Device information is only added when it has been confirmed from a real watch face package, device information, or another reliable source. Unknown devices are not given guessed resolutions or preview dimensions.

## Requirements

* Python 3.10 or newer
* PyQt6
* Pillow

## Installation

Clone the repository and install the dependencies:

```bash
git clone https://github.com/VortexWatch/WatchDialEdit.git
cd WatchDialEdit
pip install -r requirements.txt
```

## Running

You can start the editor with:

```bash
python main.py
```
The folder should contain an `iwf.json` file and the assets referenced by it.

You can also open a folder from the application with:

**File → Open Watch Face…**

## Editing a watch face

Once a design is open, the main window provides the canvas, layer list, inspector, and asset tools.

Common operations:

| Operation       | Action                                            |
| --------------- | ------------------------------------------------- |
| Add widget      | **Edit → Add Widget…**                            |
| Edit properties | Select an item and use the Inspector              |
| Select an asset | Use **Browse…** in the Inspector                  |
| Set watch hands | Select a watch item and use the Watch Hands panel |
| Undo            | `Ctrl+Z`                                          |
| Redo            | `Ctrl+Y`                                          |
| Export Watch Face   | **File → Export Watch Face…**                           |
| Export preview  | **File → Export Preview PNG…**                    |

## Widget support

The editor currently has support for a range of widgets found in IWF watch faces, including:

* Time
* Hour / minute / second digits
* Date
* Day and weekday
* Month and year
* AM/PM
* Heart rate
* Steps
* Calories
* Distance
* Battery
* Weather
* Unit labels
* Text and icon content
* App shortcuts
* Status icons
* Animations
* Watch hands
* Rings
* Progress bars
* Arc meters
* Rotating pointer / multimeter widgets
* Icon + digit combinations
* Custom progress digits

The available fields also depend on the widget type and the device format.

## Project structure

```text
WatchDialEdit/
├── watchdialedit/
│   ├── core/
│   │   ├── iwf_model.py
│   │   ├── font_doc.py
│   │   ├── assets.py
│   │   ├── project.py
│   │   ├── preview_state.py
│   │   ├── renderer.py
│   │   ├── pixel_codec.py
│   │   ├── lz4block.py
│   │   ├── iwf_packer.py
│   │   ├── widget_catalog.py
│   │   └── devices.py
│   ├── ui/
│   │   ├── model.py
│   │   ├── canvas.py
│   │   ├── panels.py
│   │   ├── new_widget_dialog.py
│   │   ├── asset_picker_dialog.py
│   │   └── main_window.py
│   └── app.py
├── main.py
├── iwf_template/
├── requirements.txt
├── LICENSE
└── README.md
```

The `core` package contains the IWF/font/asset handling and rendering code. It does not depend on PyQt6.

The `ui` package contains the PyQt6 editor.

## Format handling

WatchDialEdit works with the files that make up an extracted IWF design, including:

```text
iwf.json
font.json
*.png
```

The editor does not create a separate project format around these files.

The `.iwf` exporter handles the container format and the image data used by the supported watch face formats. LZ4 block compression (For _24bit models) is implemented in Python.

## Known limitations

There are still parts of the format that are not completely understood.

In particular:

* Device information for most devices has not been verified yet.
* Some widget rendering behavior still needs to be compared with an actual watch.
* Some animation and pointer behavior is incomplete.
* Some device-specific pixel formats still need confirmation.
* The generated LZ4 data is valid, but is not guaranteed to be byte-for-byte identical to the reference encoder.

These cases are intentionally left marked as unknown rather than being filled in with guesses.

## Contributing

Contributions are welcome.

Useful contributions include:

* Confirming support for additional devices
* Testing exported watch faces on real hardware
* Improving widget rendering
* Fixing format handling
* Adding tests
* Documenting previously unknown IWF fields

When documenting a device or format detail, please include where the information came from. Unknown values should be left unknown rather than guessed.

## Disclaimer

WatchDialEdit is an independent project and is not affiliated with or endorsed by Shenzhen DO Intelligent Technology Co., Ltd. (idoosmart) or any smartwatch manufacturer.

The weather, ring, or progressbar widgets may render incorrectly.

This is CloudFaceCreate, but we decided to rename it to WatchDialEdit.

## License
GNU General Public License V3.0
