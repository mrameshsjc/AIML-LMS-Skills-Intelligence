# app/domain – the engine's own data objects

**Filled in:** Phase 5.

Simple dataclasses such as `Employee`, `Skill`, `RoleRequirement`, `Course` and `Enrollment`. Every repository returns these, whatever the data source, so services never depend on CSV columns or table names.
