# Word equation repair notes

## Why the square appears after summation

The conversion path used by this skill is:

1. Markdown LaTeX formula
2. controlled MathML
3. Microsoft Office `MML2OMML.XSL`
4. Word OMML inside `word/document.xml`

For formulas such as:

```latex
E_{voyage}=\sum_{i=1}^{N}P_{save,i}\Delta t_i
```

Office's XSLT sometimes converts the summation sign into an OMML `m:nary` element but leaves its body element `m:e` empty. The actual following term, such as `P_save,i`, is emitted as a sibling after the `m:nary`. Word renders the empty `m:e` as a dotted placeholder square, so the formula looks like `Σ □ P_save`.

## Repair strategy

After saving the `.docx`, unzip it, parse `word/document.xml`, and find every empty n-ary body:

```xpath
//m:nary[m:e[not(.//m:t)]]
```

For each matching `m:nary`, move the immediate following sibling into the empty `m:e` node. This restores the intended Word equation structure:

```xml
<m:nary>
  ...
  <m:e>
    <!-- moved P_save,i or M_fuel,j here -->
  </m:e>
</m:nary>
```

Then rezip the DOCX.

## Validation checklist

- The output file opens in Word without repair prompts.
- Display formulas are editable Word equations.
- Inline formulas are editable Word equations where mapping is available.
- `raw_dollar_count` should normally be `0`.
- `empty_nary_count` after repair should be `0`.
- Manually inspect formulas containing `\sum`, `\int`, products, or large operators.

## Keep this behavior

Do not remove the n-ary repair just because one document looks fine. The issue depends on the exact MathML structure and Office transform behavior, so it may reappear with another summation or fraction formula.
