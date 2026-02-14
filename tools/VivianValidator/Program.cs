using System;
using System.IO;
using System.Text.Json;

namespace VivianValidator
{
    public static class Program
    {
        public static int Main(string[] args)
        {
            string? schemaPath = null;
            string? bundleUrl = null;

            foreach (string arg in args)
            {
                if (arg.StartsWith("--schema=", StringComparison.OrdinalIgnoreCase))
                {
                    schemaPath = arg.Substring("--schema=".Length).Trim('"');
                }
                else if (arg.StartsWith("--input-dir=", StringComparison.OrdinalIgnoreCase))
                {
                    string path = arg.Substring("--input-dir=".Length).Trim('"');
                    bundleUrl = path;
                }
                else if (arg.StartsWith("--bundle-url=", StringComparison.OrdinalIgnoreCase))
                {
                    bundleUrl = arg.Substring("--bundle-url=".Length).Trim('"');
                }
            }

            schemaPath ??= FindSchemaPath();
            bundleUrl ??= FindDefaultInputDir();

            if (schemaPath == null)
            {
                Console.Error.WriteLine("Schema path not found. Use --schema=<path>.");
                return 2;
            }

            if (bundleUrl == null)
            {
                Console.Error.WriteLine("Input directory not found. Use --input-dir=<path> or --bundle-url=<path>.");
                return 2;
            }

            var result = ValidatorRunner.Execute(schemaPath, bundleUrl);
            var json = JsonSerializer.Serialize(result, new JsonSerializerOptions
            {
                WriteIndented = true
            });
            Console.WriteLine(json);

            return result.Ok ? 0 : 1;
        }

        private static string? FindDefaultInputDir()
        {
            string cwd = Directory.GetCurrentDirectory();
            string candidate = Path.Combine(cwd, "generated_specs");
            return Directory.Exists(candidate) ? candidate : cwd;
        }

        private static string? FindSchemaPath()
        {
            string cwd = Directory.GetCurrentDirectory();
            DirectoryInfo? dir = new DirectoryInfo(cwd);
            while (dir != null)
            {
                string candidate = Path.Combine(dir.FullName, "schemas", "FunctionalSpecification.schema.json");
                if (File.Exists(candidate))
                {
                    return candidate;
                }
                dir = dir.Parent;
            }

            return null;
        }
    }
}
