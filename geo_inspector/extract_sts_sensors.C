// Default output: data/output/sensors.csv relative to this macro's directory.
#include <TFile.h>
#include <TKey.h>
#include <TClass.h>
#include <TGeoManager.h>
#include <TGeoVolume.h>
#include <TGeoNode.h>
#include <TGeoMatrix.h>
#include <TGeoBBox.h>
#include <TSystem.h>
#include <TString.h>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <regex>
#include <memory>

namespace sts_inspector {
std::string quote(const std::string& value) {
    std::string result = "\"";
    for (char c : value) result += (c == '"' ? "\"\"" : std::string(1, c));
    return result + "\"";
}

void walk(TGeoVolume* volume, const TGeoHMatrix& global, const std::string& path,
          std::ostream& output, unsigned& count) {
    static const std::regex sensorPattern("Sensor[0-9]+");
    if (std::regex_match(volume->GetName(), sensorPattern)) {
        auto* box = dynamic_cast<TGeoBBox*>(volume->GetShape());
        if (!box || volume->GetShape()->IsA() != TGeoBBox::Class())
            throw std::runtime_error("Expected a box sensor at " + path);
        double center[3];
        global.LocalToMaster(box->GetOrigin(), center);
        output << quote(path);
        for (double v : center) output << ',' << v;
        // Full dimensions in the sensor's own axes; ROOT getters are half lengths.
        output << ',' << 2 * box->GetDX() << ',' << 2 * box->GetDY()
               << ',' << 2 * box->GetDZ();
        const double* rotation = global.GetRotationMatrix();
        for (int i = 0; i < 9; ++i) output << ',' << rotation[i];
        output << '\n';
        ++count;
    }
    for (int i = 0; i < volume->GetNdaughters(); ++i) {
        auto* child = volume->GetNode(i);
        TGeoHMatrix transform(global);
        transform.Multiply(child->GetMatrix());
        walk(child->GetVolume(), transform, path + "/" + child->GetName(), output, count);
    }
}

void extract(const char* input, const char* output) {
    if (std::string(input) == output) throw std::runtime_error("Input and output must differ");
    std::unique_ptr<TFile> file(TFile::Open(input, "READ"));
    if (!file || file->IsZombie()) throw std::runtime_error("Cannot open geometry file");
    TGeoManager* manager = nullptr;
    TGeoVolume* volume = nullptr;
    TGeoMatrix* placement = nullptr;
    // Inspect classes first: do not deserialize both a manager and its exported volumes.
    TIter next(file->GetListOfKeys());
    while (auto* key = dynamic_cast<TKey*>(next())) {
        auto* cls = TClass::GetClass(key->GetClassName());
        if (cls && cls->InheritsFrom(TGeoManager::Class())) {
            if (manager) throw std::runtime_error("Multiple geometry managers in file");
            manager = dynamic_cast<TGeoManager*>(key->ReadObj());
        }
    }
    TGeoHMatrix transform;
    std::string path;
    if (manager) {
        auto* top = manager->GetTopNode();
        if (!top) throw std::runtime_error("Geometry has no top node");
        volume = top->GetVolume();
        transform.Multiply(top->GetMatrix());
        path = std::string("/") + top->GetName();
    } else {
        next.Reset();
        while (auto* key = dynamic_cast<TKey*>(next())) {
            auto* cls = TClass::GetClass(key->GetClassName());
            if (cls && cls->InheritsFrom(TGeoVolume::Class())) {
                if (volume) throw std::runtime_error("Multiple exported volumes in file");
                volume = dynamic_cast<TGeoVolume*>(key->ReadObj());
            } else if (cls && cls->InheritsFrom(TGeoMatrix::Class())) {
                if (placement) throw std::runtime_error("Multiple placement matrices in file");
                placement = dynamic_cast<TGeoMatrix*>(key->ReadObj());
            }
        }
        if (!volume) throw std::runtime_error("No TGeoManager or TGeoVolume found");
        if (!placement) throw std::runtime_error("Volume export has no global placement matrix");
        transform.Multiply(placement);
        // Exported volumes have no top node. This is a volume-rooted debug path.
        path = std::string("/") + volume->GetName();
    }
    std::ostringstream rows;
    rows << std::setprecision(17);
    unsigned count = 0;
    walk(volume, transform, path, rows, count);
    if (!count) throw std::runtime_error("No SensorNN placements found");
    std::ofstream stream(output);
    if (!stream) throw std::runtime_error("Cannot open sensor CSV output");
    stream << "node_path,x,y,z,dx,dy,dz,r00,r01,r02,r10,r11,r12,r20,r21,r22\n" << rows.str();
    stream.close();
    if (!stream) throw std::runtime_error("Failed writing sensor CSV");
    std::cout << "Extracted " << count << " sensor placements to " << output << '\n';
}
} // namespace sts_inspector

void extract_sts_sensors(const char* input, const char* output = "sensors.csv") {
    try {
        TString destination(output);
        if (!destination.BeginsWith("/")) {
            TString directory = gSystem->DirName(__FILE__);
            destination = directory + "/data/output/" + destination;
        }
        TString parent = gSystem->DirName(destination.Data());
        if (gSystem->AccessPathName(parent.Data()) && gSystem->mkdir(parent.Data(), kTRUE) != 0)
            throw std::runtime_error("Cannot create output directory: " + std::string(parent.Data()));
        sts_inspector::extract(input, destination.Data());
    }
    catch (const std::exception& error) {
        std::cerr << "extract_sts_sensors: " << error.what() << '\n';
        gSystem->Exit(1);
    }
}
