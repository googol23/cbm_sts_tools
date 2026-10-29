#include "/u/dramirez/WORK/plotting/tools/ToolTHCompare.h"

#include <TDirectory.h>
#include <TFile.h>
#include <TH1.h>

#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace
{
  void CheckFile(const TFile* file, const std::string& name)
  {
    if (!file || file->IsZombie()) throw std::runtime_error("cannot open " + name);
  }
}

void compare_matbudget(
  std::string f_name_0 = "data/input/sts_matbudget_v22d.merged.root",
  std::string f_name_1 = "data/input/sts_matbudget_v26a.merged.root",
  std::string f_name_o = "data/output/compare_matbudget.root"
)
{
  std::unique_ptr<TFile> first(TFile::Open(f_name_0.c_str(), "READ"));
  std::unique_ptr<TFile> second(TFile::Open(f_name_1.c_str(), "READ"));

  CheckFile(first.get(), f_name_0);
  CheckFile(second.get(), f_name_1);

  const auto found = ToolTHCompare::GetTHPaths(first.get());
  std::vector<std::string> paths;
  paths.reserve(found.th1.size() + found.th2.size());
  paths.insert(paths.end(), found.th1.begin(), found.th1.end());
  paths.insert(paths.end(), found.th2.begin(), found.th2.end());

  std::unique_ptr<TFile> output(TFile::Open(f_name_o.c_str(), "RECREATE"));
  CheckFile(output.get(), f_name_o.c_str());

  int compared = 0;
  int missing  = 0;
  int failed   = 0;

  for (const auto& path : paths) {
    TH1* firstHistogram  = nullptr;
    TH1* secondHistogram = nullptr;
    first->GetObject(path.c_str(), firstHistogram);
    second->GetObject(path.c_str(), secondHistogram);

    if (!firstHistogram || !secondHistogram) {
      std::cerr << "WARNING: missing histogram: " << path << '\n';
      ++missing;
      continue;
    }

    try {
      auto result = ToolTHCompare::CompareTH(
        *firstHistogram, *secondHistogram, ToolTHCompare::NormalizedDifference
      );

      const std::string directoryName = ToolTHCompare::SanitizeName(path);
      TDirectory* directory           = output->mkdir(directoryName.c_str());
      if (!directory) throw std::runtime_error("cannot create output directory: " + directoryName);
      result.Write(*directory);

      std::cout << path << "  chi2=" << result.chi2 << "  ndof=" << result.ndof
                << "  chi2/ndof=" << result.Chi2PerBin() << '\n';
      ++compared;
    }
    catch (const std::exception& error) {
      std::cerr << "ERROR comparing " << path << ": " << error.what() << '\n';
      ++failed;
    }
  }

  output->Write();
  output->Close();

  std::cout << "\n==========================================\n"
            << "Material-budget histogram comparison\n"
            << "Output   : compare_matbudget.root\n"
            << "Compared : " << compared << '\n'
            << "Missing  : " << missing << '\n'
            << "Failed   : " << failed << '\n'
            << "==========================================\n";
}
