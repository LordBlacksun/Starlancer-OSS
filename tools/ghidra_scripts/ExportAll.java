// ExportAll.java - Ghidra headless post-script for the Starlancer RE project.
// After auto-analysis, exports: a function index CSV, a single decompiled-C
// file (all functions), defined strings, and the symbol table. Output dir is
// passed as the first script arg (-postScript ExportAll.java <outDir>).
//
// @category Starlancer
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.decompiler.DecompiledFunction;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolTable;
import ghidra.util.task.ConsoleTaskMonitor;
import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;

public class ExportAll extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        File outDir = new File(args.length > 0 ? args[0] : "exports");
        outDir.mkdirs();
        String base = currentProgram.getName();
        FunctionManager fm = currentProgram.getFunctionManager();

        // 1) Function index CSV
        File csv = new File(outDir, base + ".functions.csv");
        try (PrintWriter pw = new PrintWriter(new FileWriter(csv))) {
            pw.println("entry,name,size,calling_convention");
            for (Function f : fm.getFunctions(true)) {
                pw.printf("%s,\"%s\",%d,%s%n", f.getEntryPoint(), f.getName(),
                        f.getBody().getNumAddresses(), f.getCallingConventionName());
            }
        }
        println("ExportAll: wrote " + csv);

        // 2) Decompile every function into one .c file (for grepping)
        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);
        ConsoleTaskMonitor mon = new ConsoleTaskMonitor();
        File cfile = new File(outDir, base + ".decompiled.c");
        int n = 0;
        try (PrintWriter pw = new PrintWriter(new FileWriter(cfile))) {
            for (Function f : fm.getFunctions(true)) {
                if (monitor.isCancelled()) break;
                DecompileResults r = dec.decompileFunction(f, 60, mon);
                if (r != null && r.decompileCompleted()) {
                    DecompiledFunction df = r.getDecompiledFunction();
                    if (df != null) {
                        pw.println("/* ==== " + f.getEntryPoint() + "  " + f.getName() + " ==== */");
                        pw.println(df.getC());
                        pw.println();
                        n++;
                    }
                }
            }
        }
        dec.dispose();
        println("ExportAll: decompiled " + n + " functions -> " + cfile);

        // 3) Defined strings
        File sfile = new File(outDir, base + ".strings.txt");
        try (PrintWriter pw = new PrintWriter(new FileWriter(sfile))) {
            DataIterator it = currentProgram.getListing().getDefinedData(true);
            for (Data d : it) {
                if (d.hasStringValue()) {
                    pw.printf("%s\t%s%n", d.getAddress(), String.valueOf(d.getValue()).replaceAll("[\\r\\n]", " "));
                }
            }
        }
        println("ExportAll: wrote " + sfile);

        // 4) Symbol table (imports / exports / labels)
        File symf = new File(outDir, base + ".symbols.txt");
        try (PrintWriter pw = new PrintWriter(new FileWriter(symf))) {
            SymbolTable st = currentProgram.getSymbolTable();
            for (Symbol s : st.getAllSymbols(true)) {
                pw.printf("%s\t%s\t%s%n", s.getAddress(), s.getSymbolType(), s.getName(true));
            }
        }
        println("ExportAll: wrote " + symf);
    }
}
