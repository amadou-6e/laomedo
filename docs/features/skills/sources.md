# Configure a Skill source

**Source** tells the Skill node where to find instruction bundles. A bundle is a
folder containing `SKILL.md`, plus its supporting files. Use one of:

- An absolute local folder path, such as `C:\CodeWorkspace\laomedo\my-skills`.
  Replace this example with your folder. The host source service must explicitly
  allow that folder. A path to `SKILL.md`
  or a `file:///` URI within an allowed root also works.
- A public HTTPS GitHub or GitLab repository-root URL, for example
  `https://github.com/your-account/skill-library`. This is an example URL to
  replace, not a configured repository. Private Git credentials and GitLab
  subgroup URLs are not supported; use an allowed local checkout instead.
- The configured registry's absolute path to browse bundles already imported.
  That registry root is recognized separately from allowed local source roots.

Leave Source empty to keep an existing exact registry reference. Entering a path
does not grant access to the host filesystem. If Langflow runs in a container,
the host service reads the host path; a Windows path does not become a container
mount automatically.

## Configure the host service once

Use the Python environment, `$pythonExe`, `$runtimeRoot` and existing private API
token from [getting started](../../getting-started.md). Start the source service
in its own terminal, pointing to the same registry used by the app:

```powershell
& $pythonExe -m laomedo.skills.interface.sources.cli `
  --registry "$runtimeRoot/registry" --state "$runtimeRoot/skill-sources" `
  --allow-local-root 'C:\CodeWorkspace\laomedo\my-skills' `
  --api-token-file "$runtimeRoot/runner/api-token" --port 8782
```

Repeat `--allow-local-root` for each additional folder. Public repository sources
do not require a local-root flag. Keep registry, state and token paths private;
never paste the token into a node or graph.

Before starting the Langflow app, set its backend connection in the app terminal:

```powershell
$env:LAOMEDO_SKILL_SOURCE_URL = 'http://127.0.0.1:8782'
$env:LAOMEDO_SKILL_SOURCE_TOKEN_FILE = "$runtimeRoot/runner/api-token"
```

For a containerized app, the supported host address is
`http://host.docker.internal:8782`; the token-file setting must point to its
existing private mounted token file. Keep the other app settings and registry
connection. These instructions describe configuration; they do not activate a
service or mount automatically.

## Select files on the node

1. Enter Source. **Discovery** reports the scan and available skills.
2. Choose **Skill**. Discovery then lists that Skill's available revisions.
3. Expand **Advanced settings** and choose **Revision**. It is an exact file
   version, not a moving latest pointer. **Base Commit** identifies the parent
   for an operation; leave it empty only for the initial imported revision.
4. Open **Skill files** to inspect the selected bundle. To change it, edit files
   and Publish there, or supply a change payload through **Operation**.

Discovery reads/imports verified files; it never runs a Skill or starts an Agent.
Refresh updates choices while preserving a valid selected revision. Changing
Source clears Skill and Revision; changing Skill clears Revision, so choose a
replacement in Advanced settings. There is no Edit Request control. Existing
saved feedback requests are retained internally for compatibility only.

If Discovery fails, check the source URL/path, the allowed local roots, and the
running host service and backend connection above. Then refresh the Skill list.
An empty result means no admitted `SKILL.md` bundles were found. Access to the
source does not grant editing or publishing permission; those are configured
separately in the [walkthrough](walkthrough.md) and
[manual workspace guide](manual-workspace.md).
