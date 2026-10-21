@echo off
rem Test run on SIMULATED demo data with the bundled Python; does not touch PostgreSQL or the installed service.
rem Runs the end-to-end flow check (plant tree -> signals -> features -> reference -> prediction configuration)
rem and then keeps a demo server open on http://127.0.0.1:8765 for manual testing. Add -Check to run the check only.
call "%~dp0pdm\tools\run_demo.cmd" %*
