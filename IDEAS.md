## Things to consider and probably do

# CID-based provenance

# Approver signatures

# Expression as description
Approval tests that only require the expression to be evaluated.
The name can be derived from the expression.  
This ties into the CID-based provenance.

There are multiple ways this can be done:

1) f-strings
2) t-strings
3) Use the code cell content.  
  * More than one way for this too and ast in Python stdlib is one.
  * Magics: %approve, %%approve

# Multiple tests in a cell
These short and even one-line tests suggest allowing more than one test in a cell.
Maybe some way to have multiple tests in a test.  This could have checkboxes and "check all".
