# Private Skill browser

`models.ts` owns explicit private selection and provenance wire records.
`api.ts` sends only same-origin, CSRF-protected private reads and never routes
through public Skill services. `PrivateSkillControls` owns the Advanced settings
connection choice and discovered private Skill/revision selectors. Changing a
connection clears dependent selections; failure preserves existing pins.
`PrivateSkillViewer` presents immutable files and retained source history without
public edit/publication hooks. All metadata and file buffers are cleared on
connection/profile invalidation; an obsolete request cannot restore them.

The node stores only opaque connection/repository references and exact source
pins. Browser memory holds private response bytes, with no persistent query cache.
The existing server release fence remains authoritative. Private Agent execution
is refused until separately specified materialization admission exists.
