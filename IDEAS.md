## Things to consider and probably do

# CID-based provenance
How do we deal with static and dynamic context for code content identification?
A simple strategy is to have the CID of the concatenated preceding code (prefix) then that of the current cell.
Or maybe the cell just has the prefix CID and the CID for whole after concatenating the current cell.
But since we could want to search by content then maybe just all three?
Dynamic is trickier but will presumably include/depend on/be computed by the kernel.

# Approver signatures
Lots of options here.
1) SSH
2) A2A
3) Any number of web3 systems.

# Expression as description
Approval tests that only require the expression to be evaluated.
The name can be derived from the expression.  
This ties into the CID-based provenance.

There are multiple ways this can be done:

1) f-strings
2) t-strings
3) Use the code cell content.  
  * More than one way for this too and ast in Python stdlib is one.
  * Magics: %approve, %%approve (DONE)
4) Test cell type
  * Getting pretty complicated but could make sense if/when code language isn't the same as tests.
  * Leads into ideas like Spec cell type.
  * When to use a cell type vs magic?  Magics definitely depend on the kernel.


# Multiple tests in a cell
These short and even one-line tests suggest allowing more than one test in a cell.
Maybe some way to have multiple tests in a test.  This could have checkboxes and "check all".
