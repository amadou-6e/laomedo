# OpenCode controller

Registered as `opencode` in `../images.json`. The shared runtime builds this
context on the selected daemon when its image is absent, verifies version
1.18.33 without inference, and uses the actual local image ID. The profile,
broker, isolated workers and credentials are supplied at runtime, never copied
into this image. Building it does not create a production OpenCode host
composition or authenticate an account.
