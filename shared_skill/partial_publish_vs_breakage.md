# Partial Package Publishing — Version Set Build Breakage

## When This Applies

When a CR or change modifies two interdependent packages (A and B) where one calls methods defined by the other, and only one of them is auto-published to the version set via the pipeline CDK.

## The Problem

In Brazil pipelines, packages are published to a version set independently. If packages A and B have a caller/callee relationship:

- **Package B** defines a method/type
- **Package A** calls/imports that method/type

If only one is in the CDK auto-publish list:
- B publishes a new API → A (old version in VS) doesn't call it yet → **OK**
- A publishes code calling B's new API → B (old version in VS) doesn't have it yet → **VS BUILD BREAKS**

The break happens because the version set tries to compile A against the old B artifact that lacks the new method/type.

## Symptoms

- Dry run builds fail for a downstream consumer package (e.g., `PDESharedDaggerModules`)
- Error is a missing method/class/type that clearly exists in the source of the other package
- The failure appeared right after a CR merged to one of the two packages
- All CR dry runs in the pipeline are blocked

## How to Fix

### Immediate (unblock pipeline)

Submit a **manual build** for the package that's missing from the VS:

1. Identify which package (A or B) hasn't published its latest code to the VS
2. Submit a manual build for that package to force-publish it
3. This unblocks the pipeline and all pending CR dry runs

### Permanent (prevent recurrence)

Add **both** packages to the CDK auto-publish list:

1. Open the pipeline's CDK package (e.g., `MarioServiceCDK/lib/app.ts`)
2. Find the packages array that maps to `pipeline.addPackageToAutobuild()`
3. Add the missing package name to the list
4. Merge the CR — both packages will now auto-publish together on future changes

## Example

```
Pipeline: MarioService-cellular
CDK Package: MarioServiceCDK
File: lib/app.ts

// Packages auto-published via:
[
    ...
    "PubTechTrafficQualityPlugin",
    "PubTechSignalsAudiencePlugin",  // ← was missing, added via CR-291837449
    "PubTechGetAdStatePlugin",
    ...
].map(pkg => pipeline.addPackageToAutobuild(getBrazilPackage(pkg)));
```

## Prevention Checklist

When onboarding a new package to auto-publish, check:

1. Does this package call methods from other packages that are also actively developed?
2. Do other packages call methods defined in this package?
3. Are ALL sides of the dependency already in the auto-publish list?
4. If not, add them together in the same CR to avoid the window where only one side publishes.

## Related

- Build Issue: `BuildIssues/009-PubTechSignalsAudiencePlugin-PartialPublish-VS-Break.md`
