# Family Face Recognition Setup

JARVIS can recognize you and family members from **local reference photos**.

Google Photos is useful because your family photos may already be grouped and named there, but Google does not give apps direct access to those private face-name labels through the public Google Photos API. So the safe setup is:

1. Open Google Photos yourself.
2. Go to a person's face group.
3. Download a few clear photos of that person.
4. Put those photos into JARVIS local folders.
5. JARVIS learns local face profiles from those folders.

This keeps family names and photos on your computer.

---

## Folder Setup

Create this folder in the JARVIS project:

```text
known_faces
```

Inside it, create one folder per person:

```text
known_faces/
  Prashant/
    photo1.jpg
    photo2.jpg
  Mummy/
    photo1.jpg
    photo2.jpg
  Papa/
    photo1.jpg
    photo2.jpg
```

Folder names become the names JARVIS uses.

Use simple names like:

```text
Prashant
Mummy
Papa
Didi
Brother
```

---

## Best Photos To Use

Use 3 to 10 photos per person.

Good photos:

- Clear face
- Front-facing
- Good light
- Not too blurry
- One main person in the photo
- Different days or angles

Avoid:

- Group photos where faces are tiny
- Dark photos
- Side-face photos
- Sunglasses or heavy masks
- Funny filters

---

## Config

In `jarvis_config.json`, keep this enabled:

```json
{
  "face_recognition_enabled": true,
  "family_face_recognition_enabled": true,
  "known_faces_dir": "known_faces",
  "face_match_tolerance": 0.55
}
```

You can also list exact files manually:

```json
{
  "known_face_images": {
    "Prashant": [
      "known_faces/Prashant/photo1.jpg",
      "known_faces/Prashant/photo2.jpg"
    ],
    "Mummy": [
      "known_faces/Mummy/photo1.jpg"
    ]
  }
}
```

Most users should use folders instead of manually listing every file.

---

## Run

Start the web app:

```bash
python jarvis_web.py --host 127.0.0.1 --port 8765
```

Open:

```text
http://localhost:8765
```

Start the camera. When a known person appears, JARVIS should label them with the folder name.

---

## Privacy Rules

Do not upload family photos to GitHub.

These folders are ignored by Git:

```text
known_faces/
owner_faces/
jarvis_photos/
```

Only use face recognition with permission from the people involved.

JARVIS should not be used for hidden monitoring, spying, or identifying people without consent.

---

## If It Does Not Work

Try these fixes:

| Problem | Fix |
|---|---|
| No faces recognized | Add clearer front-facing photos |
| Wrong person matched | Lower `face_match_tolerance`, for example `0.50` |
| Too strict/no matches | Raise `face_match_tolerance`, for example `0.60` |
| Package missing | Install `face_recognition` and its dependencies |
| Camera works but names do not | Check folder names and image files |

Start with one person first. After that works, add more family members.
