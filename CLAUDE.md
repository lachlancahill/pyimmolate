## Context

I want to make a python wrapper for https://github.com/SpectralPack/Immolate to 
allow the user to use a python library to define seed filters. 

While this will only work on windows (because the immolate dependency is windows only), development will take place on this mac, so you will not
be able to do any testing, you'll need to leave it to me to sync my code with my windows machine
to run tests.

## Imagined Process Flow

I imagine this working like the below, but haven't thought about this in detail, and don't have a detailed 
understanding of how the Immolate app works:

This should be a pypi package that someone can just `pip install pyimmolate`

It will:

* Automatically download and cache the immolate app from their github releases tab (small file)
* Allow the user to define and add completely customisable filter criteria, with all the filters in 
    [example_filters](example_filters), but this should be pythonic
* It should then be able to convert this into a working .cl file and spin up an immolate subprocess to run immolate 
    with that file and stream the response.

## General coding principles

* Avoid Try/except blocks, it is better to fail early and raise errors so they can be debugged.
* No command line arguments should be used. Any hardcoded parameters should be in a constants submodule (EG Immolate version)

## Task

* Read some of the [example_filters](example_filters) which come with Immolate to understand how filtering is done.
* Read [DESIGN.md](DESIGN.md), ask any clarifying questions you have, then implement this solution completely. 