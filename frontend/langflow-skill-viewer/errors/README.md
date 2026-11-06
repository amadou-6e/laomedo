# Shared error presentation

`describeNodeFailure` parses only declared failure slots and projects safe diagnostic identifiers through the catalogue. `ErrorExplanation` owns recovery prose; `ErrorPopup` and `NodeErrorNotice` compose it for their surfaces. `CopyIcon` copies only the safe projection. This package is deployed to Langflow components/laomedoErrors; recovery controls belong to the separate recovery package.
