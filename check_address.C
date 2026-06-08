/**
 * This macro uses the dumnp created by collect_test use to build the sts addresses
 * 
 * The pourpose is to validate that the python implementation of CbmStsAddress match the CBMROOT class CbmStsAddress
 */

bool check_address(std::string dump_file = "STS_NAME_TO_ADDRESS_DUMP.dump"){
  ifstream dump(dump_file);
  std::string line;

  std::unique_ptr<CbmStsAnalysis> run = std::make_unique<CbmStsAnalysis>();

  int failed_checks = 0;
  while (std::getline(dump, line)){
    auto ss = std::stringstream(line);
    int unit, ladder, half_ladder, module, sensor, side, version, address;
    ss >> unit >> ladder >> half_ladder >> module >> sensor >> side >> version >> address;

    int32_t cbm_sts_address = CbmStsAddress::GetAddress(unit, ladder, half_ladder, module, sensor, side, version);

    auto compare_status = (address == cbm_sts_address) ? " PASSED " : " FAILED ";
    if (address != cbm_sts_address){
      std::cout << address << "\t" << cbm_sts_address << compare_status << std::endl;
      failed_checks++;
    }
  }

  if (failed_checks){
    std::cout << "Address validation: FAILED\n";
    std::cout << "No of failed comparisons: " << failed_checks << std::endl;
    return false;
  }

  
  std::cout << "Address validation: Passed\n";
  return true;
}