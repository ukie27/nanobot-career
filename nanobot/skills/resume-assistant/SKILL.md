---
name: resume-assistant
description: Help users import, understand, review, and improve resumes for job search scenarios. Use when the user asks to analyze a resume, extract candidate profile information from a resume, manage resume versions, optimize a resume for a role, or adapt a resume to a JD.
---

# Resume Assistant

Use this skill for resume-related job search work. The goal is to help the user improve their resume while also keeping a reusable candidate profile for later job matching, application messages, and interview preparation.

## Storage Model

Use the `career_resume` tool for persistent data:
- `import`: save a pasted/text resume, store a resume version, and update the candidate profile with information you extracted.
- `profile`: read the current candidate profile.
- `update_profile`: update confirmed profile fields.
- `list`: list resume versions.
- `get` or `get_default`: read a resume version for review or optimization.
- `save_version`: save an optimized resume only after the user accepts or asks to save it.
- `set_default`: set a resume as the default version.

Do not save every diagnosis or draft by default. Resume reviews and rewrite suggestions are normally conversation output only. Save a new resume version only when the user asks to save it or clearly accepts the optimized version.

## Importing A Resume

When the user provides a resume:
1. Extract candidate profile fields from the resume.
2. Call `career_resume` with `action="import"`.
3. Store extracted fields as concise plain text, not JSON.
4. Return a short summary of what was saved and what still needs confirmation.

Important profile fields:
- Basic: name, phone, email, location.
- Education: education, school, major, graduation date.
- Goals: target roles, target cities, expected salary if present.
- Experience: skills, project experiences, internship experiences, campus experiences.
- Extras: awards, certificates, preferences, constraints, weaknesses.

Only extract facts present in the resume or stated by the user. Do not invent experience, metrics, awards, dates, or technologies.

## Reviewing A Resume

For a general resume review, read the default resume if needed and assess:
- Target clarity: what role this resume currently fits.
- Content quality: whether each section shows responsibility, action, and result.
- Project strength: depth, ownership, technical detail, and measurable outcome.
- Keyword coverage: skills and terms likely needed for the target role.
- Risk: vague claims, unsupported metrics, inflated wording, missing context.

Preferred output:
```text
结论
- ...

主要问题
1. ...

可直接修改的地方
- 原文：
- 建议：
- 原因：

需要用户补充的信息
- ...
```

## Optimizing For A Role Or JD

When optimizing for a target role or JD:
1. Read the default or requested resume.
2. Compare resume content with the target role/JD.
3. Give matching points, gaps, and rewrite suggestions.
4. Provide replacement text for specific sections.
5. Ask before saving the full optimized version unless the user already asked to save it.

If the user asks to save the optimized resume, call `career_resume` with `action="save_version"` and pass the full optimized resume text as `content`.

## Writing Rules

- Keep facts truthful.
- Do not fabricate metrics. Use placeholders such as `[补充 QPS/用户量/准确率]` when useful.
- Prefer stronger structure and clearer impact over exaggerated language.
- If information is missing, say what to add instead of pretending it exists.
- Keep the user-facing result practical: diagnosis, concrete edits, and next step.
