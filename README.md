# shadow-falls

## Example: steps for creating Chapter 7.
The following describes all the steps performed to create Chapter 7, the last example
chapter in this repository.

### Creating chapter directory
Using the following command, out script will create a new subfolder with a `config.yaml`
and and empty `edited.txt`. The latter will eventually contain the finalized version
of the chapter.

`python .\tst.py -p series -c 7 -a NEW_CHAPTER`

### Updating metadata
In order to write a new chapter, the script needs some information about what has happened
in the story so far. In particular, we need
* The last N words of the previous chapter as a writing sample for consistency.
* A summary of what happened in the story so far.

While the text of the previous chapter could be obtained on the fly, the summary is a bit
more tricky. To generate the summary, the script would need information of ALL previous
chapters. Depending on how big the overall book is, pulling in that much content would
explode the context window of many LLMs. For that reason, we precompute the summary based
on the last chapter and a summary of what has happened so far. We then store the data in
a project-level file called `properties.yaml`.

The following command summarizes chapter 6 (notice the `-c 6` parameter). We need to do this
once before writing the draft for chapter 7:

`python .\tst.py -p series -c 6 -a UPDATE_METADATA`
